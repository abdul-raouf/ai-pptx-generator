import asyncio
from models.schemas import Job, JobStage
from agents.intent_agent import IntentAgent
from agents.knowledge_agent import KnowledgeAssessmentAgent
from agents.storyboard_agent import StoryboardAgent
from agents.verification_agent import VerificationAgent
from agents.rendering_agent import RenderingAgent
from services.db import save_job
from services.sse import emit

MAX_STORYBOARD_ATTEMPTS = 2


async def advance(job: Job, user_message: str) -> str:

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
            job.stage = JobStage.STORYBOARD_GENERATION
            save_job(job)
            asyncio.create_task(run_generation_pipeline(job))
            return "Got it. Building your presentation now — I'll let you know when it's ready."

    if job.stage == JobStage.CONTEXT_REQUEST:
        if user_message.strip().lower() != "skip":
            job.user_context_text = user_message
        job.stage = JobStage.STORYBOARD_GENERATION
        save_job(job)
        asyncio.create_task(run_generation_pipeline(job))
        return "Perfect. Building your presentation now — I'll let you know when it's ready."

    return "Your presentation is being generated. Please wait."


async def run_generation_pipeline(job: Job):
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

            job.stage = JobStage.STORYBOARD_VERIFICATION
            save_job(job)

            verification = verification_agent.run(job.intent, storyboard)
            job.verification = verification

            if verification.passes:
                break

            job.user_context_text = (
                (job.user_context_text or "") +
                "\n\nPrevious attempt issues:\n" +
                "\n".join(f"- {fix}" for fix in verification.fixes_required)
            )

        job.stage = JobStage.PPTX_GENERATION
        save_job(job)

        pptx_path = rendering_agent.run(
            job_id=job.job_id,
            template_name=job.selected_template,
            storyboard=job.storyboard
        )
        job.pptx_path = pptx_path
        job.stage = JobStage.COMPLETE
        save_job(job)
        await emit(job.job_id, {
            "type": "complete",
            "message": f"Your presentation is ready — {job.storyboard.total_slides} slides generated.",
            "download_url": f"/api/v1/jobs/{job.job_id}/download"
        })

    except Exception as e:
        job.stage = JobStage.FAILED
        job.error = str(e)
        save_job(job)
        await emit(job.job_id, {
            "type": "error",
            "message": f"Something went wrong: {str(e)}"
        })