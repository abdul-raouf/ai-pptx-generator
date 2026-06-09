import asyncio
from models.schemas import Job, JobStage
from agents.intent_agent import IntentAgent
from agents.knowledge_agent import KnowledgeAssessmentAgent
from agents.storyboard_agent import StoryboardAgent
from agents.verification_agent import VerificationAgent
from agents.rendering_agent import RenderingAgent
from agents.chart_agent import ChartAgent
from agents.data_parsing_agent import DataParsingAgent


from services.db import save_job
from services.sse import emit
from services.chart_generator import (
     load_data_from_file, generate_chart
)

MAX_STORYBOARD_ATTEMPTS = 2
import time
DEBUG = True
def dbg(msg):
    if DEBUG:
        print(f"[DEBUG {time.strftime('%H:%M:%S')}] {msg}")


async def advance(job: Job, user_message: str) -> str:
    dbg(f">> advance() stage={job.stage.value}, msg_len={len(user_message)}")

    if job.stage == JobStage.INTENT_ANALYSIS:
        intent = IntentAgent().run(user_message)
        job.intent = intent
        job.original_prompt = user_message
        job.stage = JobStage.TEMPLATE_SELECTION
        save_job(job)

        template_hint = intent.suggested_template.replace("_", " ").title()
        return (
            f"Got it. You need a {intent.presentation_type.replace('_', ' ').title()} "
            f"for {intent.audience}.\n\n"
            f"Please choose a template:\n\n"
            f"[1] Corporate — Clean executive layout, formal tone\n"
            f"[2] Sales — Bold accents, persuasive structure\n"
            f"[3] Project Update — Status-focused, milestone layout\n\n"
            f"(Based on your request, I'd suggest {template_hint}.)\n\n"
            f"Type 1, 2, or 3."
        )

    if job.stage == JobStage.TEMPLATE_SELECTION:
        template_map = {"1": "corporate", "2": "sales", "3": "project_update"}
        job.selected_template = template_map.get(user_message.strip(), "corporate")
        job.stage = JobStage.KNOWLEDGE_ASSESSMENT
        save_job(job)

        assessment = KnowledgeAssessmentAgent().run(job.intent)
        job.knowledge_assessment = assessment

        if assessment.is_sufficient:
            job.stage = JobStage.STORYBOARD_GENERATION
            save_job(job)

            # If user already supplied data in their prompt, store it
            if job.intent.contains_user_data:
                job.user_context_text = (
                    (job.user_context_text or "") +
                    "\n\nUser supplied this data in their original request:\n" +
                    job.original_prompt
                )
                save_job(job)


            dbg(f">> TEMPLATE_SELECTION: kickoff run_generation_pipeline, contains_user_data={job.intent.contains_user_data}")
            asyncio.create_task(run_generation_pipeline(job))
            return (
                f"{job.selected_template.replace('_', ' ').title()} template selected. "
                f"Building your presentation now — I'll let you know when it's ready."
            )
        else:
            job.stage = JobStage.CLARIFYING_QUESTIONS
            save_job(job)
            questions = "\n".join(
                f"{i+1}. {q}"
                for i, q in enumerate(assessment.clarifying_questions)
            )
            return (
                f"Before I start, I have a few questions:\n\n{questions}\n\n"
                f"Please answer each one."
            )

    if job.stage == JobStage.CLARIFYING_QUESTIONS:
        job.clarification_answers.append(user_message)

        if job.knowledge_assessment.needs_user_context:
            job.stage = JobStage.CONTEXT_REQUEST
            save_job(job)
            return (
                "Thanks. If you have any reference material paste it here.\n\n"
                "Otherwise type skip to continue."
            )
        else:
            dbg(f">> CLARIFYING_QUESTIONS: kickoff run_generation_pipeline")
            job.stage = JobStage.STORYBOARD_GENERATION
            save_job(job)
            asyncio.create_task(run_generation_pipeline(job))
            return "Got it. Building your presentation now — I'll let you know when it's ready."

    if job.stage == JobStage.CONTEXT_REQUEST:
        dbg(f">> CONTEXT_REQUEST: kickoff run_generation_pipeline")
        if user_message.strip().lower() != "skip":
            job.user_context_text = user_message
        job.stage = JobStage.STORYBOARD_GENERATION
        save_job(job)
        asyncio.create_task(run_generation_pipeline(job))
        return "Perfect. Building your presentation now — I'll let you know when it's ready."

    if job.stage == JobStage.CHART_DATA_COLLECTION:
        dbg(f">> CHART_DATA_COLLECTION: handle_chart_data, idx={job.current_chart_index}/{len(job.chart_slides)}")
        result = await handle_chart_data(job, user_message)
        dbg(f">> CHART_DATA_COLLECTION: returned, stage now={job.stage.value}, idx={job.current_chart_index}")
        return result

    dbg(f">> advance() fell through — stage={job.stage.value}")
    return "Your presentation is being generated. Please wait."

    return "Your presentation is being generated. Please wait."


async def run_generation_pipeline(job: Job):
    dbg(f">> run_generation_pipeline() START job={job.job_id[:8]}...")
    try:
        storyboard_agent   = StoryboardAgent()
        verification_agent = VerificationAgent()
        rendering_agent    = RenderingAgent()

        while job.storyboard_attempts < MAX_STORYBOARD_ATTEMPTS:
            job.storyboard_attempts += 1
            job.stage = JobStage.STORYBOARD_GENERATION
            save_job(job)

            storyboard = storyboard_agent.run(
                intent=job.intent,
                original_prompt=job.original_prompt,
                clarification_answers=job.clarification_answers,
                user_context=job.user_context_text
            )
            job.storyboard = storyboard
            dbg(f">> storyboard done: {storyboard.total_slides} slides")

            job.stage = JobStage.STORYBOARD_VERIFICATION
            save_job(job)

            verification = verification_agent.run(job.intent, storyboard)
            job.verification = verification
            dbg(f">> verification: passes={verification.passes}")

            if verification.passes:
                break

            job.user_context_text = (
                (job.user_context_text or "") +
                "\n\nPrevious attempt issues:\n" +
                "\n".join(f"- {fix}" for fix in verification.fixes_required)
            )

        chart_agent   = ChartAgent()
        dbg(f">> identifying chart slides...")
        chart_slides  = chart_agent.identify_chart_slides(job.storyboard)
        dbg(f">> chart slides identified: {chart_slides}")
        job.chart_slides = chart_slides

        if chart_slides:
            dbg(f">> chart_slides found: {len(chart_slides)} slides need charts")
            job.stage               = JobStage.CHART_DATA_COLLECTION
            job.current_chart_index = 0
            save_job(job)

            data_source = None

            first_slide   = job.storyboard.slides[chart_slides[0]]

            if job.intent.contains_user_data:
                 # Data already in the original prompt — process first chart automatically
                 # by calling handle_chart_data with the original prompt as the "message"
                data_source = job.original_prompt
                dbg(f">> data_source = original_prompt (contains_user_data=True)")
            elif job.user_context_text:
                data_source = job.user_context_text
            elif job.clarification_answers:
                # Check if any clarification answer looks like data (long and contains commas)
                for answer in job.clarification_answers:
                    if len(answer) > 200 and answer.count(',') > 10:
                        data_source = answer
                        break
            
            if data_source:
                dbg(f">> AUTO-PROCESS: data_source len={len(data_source)}, charts={len(chart_slides)}")
                # Auto-process all chart slides with the supplied data
                total = len(job.chart_slides)
                while job.current_chart_index < total:
                    ci = job.current_chart_index + 1
                    si = job.chart_slides[job.current_chart_index]
                    slide_title = job.storyboard.slides[si].slide_title
                    await emit(job.job_id, {
                        "type": "progress",
                        "message": f"Processing chart {ci}/{total}: {slide_title}…"
                    })

                    idx_before = job.current_chart_index
                    dbg(f">> calling handle_chart_data for chart {ci}")
                    reply = await handle_chart_data(job, data_source)
                    dbg(f">> handle_chart_data returned, stage={job.stage.value}, idx={job.current_chart_index}")

                    # If handle_chart_data processed all charts it emits "complete" itself
                    if job.stage in (JobStage.PPTX_GENERATION, JobStage.COMPLETE):
                        dbg(f">> AUTO-PROCESS: all charts done, returning (complete emitted inside handle_chart_data)")
                        return

                    # If the index didn't advance, handle_chart_data hit an error —
                    # emit it to the user and stop looping (don't retry the same bad data)
                    if job.current_chart_index == idx_before:
                        await emit(job.job_id, {
                            "type":    "chart_data_needed",
                            "message": reply
                        })
                        return
            else:
                # No data supplied — ask the user
                first_slide = job.storyboard.slides[chart_slides[0]]
                await emit(job.job_id, {
                    "type":    "chart_data_needed",
                    "message": (
                        f"Storyboard ready. I found {len(chart_slides)} slides that need charts.\n\n"
                        f"Let's start with slide {chart_slides[0] + 1} — "
                        f"**{first_slide.slide_title}**\n\n"
                        f"{first_slide.key_message}\n\n"
                        f"Paste the data for this chart, or provide a file path.\n"
                        f"Type **skip** to use a placeholder instead."
                    )
                })
                return
        
        # No charts needed — go straight to rendering
        dbg(f">> NO CHARTS needed — rendering directly")
        job.stage = JobStage.PPTX_GENERATION
        save_job(job)

        dbg(f">> rendering PPTX...")
        pptx_path = rendering_agent.run(
            job_id=job.job_id,
            template_name=job.selected_template,
            storyboard=job.storyboard,
            chart_data=job.chart_data
        )
        job.pptx_path = pptx_path
        job.stage = JobStage.COMPLETE
        save_job(job)
        dbg(f">> PPTX ready: {pptx_path}, emitting 'complete' to SSE queue...")
        await emit(job.job_id, {
            "type": "complete",
            "message": f"Your presentation is ready — {job.storyboard.total_slides} slides generated.",
            "download_url": f"/api/v1/jobs/{job.job_id}/download"
        })

    except Exception as e:
        dbg(f">> ERROR in run_generation_pipeline: {type(e).__name__}: {e}", )
        import traceback; traceback.print_exc()
        job.stage = JobStage.FAILED
        job.error = str(e)
        save_job(job)
        await emit(job.job_id, {
            "type": "error",
            "message": f"Something went wrong: {str(e)}"
        })


async def handle_chart_data(job: Job, user_message: str) -> str:
    chart_agent  = ChartAgent()
    current_idx  = job.current_chart_index
    slide_index  = job.chart_slides[current_idx]
    slide        = job.storyboard.slides[slide_index]
    slide_context = f"{slide.slide_title}: {slide.key_message}"
    dbg(f">> handle_chart_data: idx={current_idx}, slide={slide_index}, data_len={len(user_message)}")

    stripped = user_message.strip()

    is_file  = stripped.endswith((".csv", ".xlsx", ".xls")) and len(stripped) < 300

    try:

        if stripped.lower() == "skip":
            job.current_chart_index += 1
            save_job(job)

            if job.current_chart_index < len(job.chart_slides):
                next_slide_index = job.chart_slides[job.current_chart_index]
                next_slide       = job.storyboard.slides[next_slide_index]
                return (
                    f"Skipped. Next: slide {next_slide_index + 1} — **{next_slide.slide_title}**\n\n"
                    f"Paste the data or a file path. Type **skip** to skip this one too."
                )
            else:
                job.stage = JobStage.PPTX_GENERATION
                save_job(job)
                rendering_agent = RenderingAgent()
                pptx_path = rendering_agent.run(
                    job_id=job.job_id,
                    template_name=job.selected_template,
                    storyboard=job.storyboard,
                    chart_data=job.chart_data
                )
                job.pptx_path = pptx_path
                job.stage = JobStage.COMPLETE
                save_job(job)
                await emit(job.job_id, {
                    "type": "complete",
                    "message": f"Your presentation is ready — {job.storyboard.total_slides} slides generated.",
                    "download_url": f"/api/v1/jobs/{job.job_id}/download"
                })
                return "Building your presentation now — I'll let you know when it's ready."
            


            
        if is_file:
            dbg(f">> handle_chart_data: loading file {stripped}")
            df = load_data_from_file(stripped)
            suggested_title = slide.slide_title
            notes = ""
        else:
            dbg(f">> handle_chart_data: calling DataParsingAgent (len={len(stripped)})")
            parsing_agent = DataParsingAgent()
            df, suggested_title, notes = parsing_agent.run(stripped, slide_context)
            dbg(f">> handle_chart_data: parsed {len(df)} rows")

        data_preview = df.head(10).to_csv(index=False)

    except Exception as e:
        dbg(f">> handle_chart_data: EXCEPTION: {type(e).__name__}: {e}")
        return (
            f"I couldn't process that data: {str(e)}\n\n"
            "Please check the format and try again, or type **skip** to use a placeholder."
        )
    dbg(f">> handle_chart_data: recommending chart type...")
    # Ask the LLM which chart type fits best
    recommendation = chart_agent.recommend_chart_type(data_preview, slide_context)
    chart_type     = recommendation["chart_type"]
    reason         = recommendation["reason"]

    # Generate the chart PNG
    dbg(f">> handle_chart_data: generating chart ({chart_type}), slide={slide_index}")
    png_path = generate_chart(df, chart_type, suggested_title or slide.slide_title, slide_index)

    # Store result
    job.chart_data[slide_index] = {
        "chart_type": chart_type,
        "png_path": png_path
    }

    job.current_chart_index += 1
    save_job(job)

    # Check if more charts are needed
    if job.current_chart_index < len(job.chart_slides):
        next_slide_index = job.chart_slides[job.current_chart_index]
        next_slide       = job.storyboard.slides[next_slide_index]
        return (
            f"Chart created — {chart_type} chart. {reason}\n\n"
            f"_{notes}_\n\n"
            f"Next: slide {next_slide_index + 1} — **{next_slide.slide_title}**\n\n"
            f"{next_slide.key_message}\n\n"
            f"Paste the data for this chart, or provide a file path.\n"
            f"Type **skip** to use a placeholder instead."
        )
    else:
        # All charts collected — start generation
        job.stage = JobStage.PPTX_GENERATION
        save_job(job)
        rendering_agent = RenderingAgent()
        pptx_path = rendering_agent.run(
            job_id=job.job_id,
            template_name=job.selected_template,
            storyboard=job.storyboard,
            chart_data=job.chart_data
        )
        job.pptx_path = pptx_path
        job.stage = JobStage.COMPLETE
        save_job(job)

        await emit(job.job_id, {
            "type": "complete",
            "message": f"Your presentation is ready — {job.storyboard.total_slides} slides generated.",
            "download_url": f"/api/v1/jobs/{job.job_id}/download"
        })
        return "All charts ready. Building your presentation now — I'll let you know when it's ready."