# # test_pipeline.py
# import asyncio
# from models.schemas import Job
# from pipeline.controller import advance
# from services.db import init_db, save_job, load_job

# async def main():
#     init_db()

#     job = Job()
#     save_job(job)

#     reply = await advance(job, "Create a sales deck for UAE banking clients targeting CFOs")
#     print("REPLY 1:", reply)
#     print("STAGE:", job.stage)

#     reply = await advance(job, "1")
#     print("REPLY 2:", reply)
#     print("STAGE:", job.stage)

#     # Give the background task a moment to finish
#     await asyncio.sleep(2)

#     job = load_job(job.job_id)
#     print("FINAL STAGE:", job.stage)
#     print("PPTX PATH:", job.pptx_path)

# asyncio.run(main())


from agents.intent_agent import IntentAgent
from agents.knowledge_agent import KnowledgeAssessmentAgent
from agents.storyboard_agent import StoryboardAgent
from agents.verification_agent import VerificationAgent
from agents.rendering_agent import RenderingAgent
import uuid



# intent = IntentAgent().run('Create a pros and cons of using Ai Agents in Government agencies')
# print(intent)

# knowledge = KnowledgeAssessmentAgent().run(intent)
# print(knowledge)

# storyboard = StoryboardAgent().run(intent,'Create a pros and cons of using Ai Agents in Government agencies', None, None)
# print("storyboard>",storyboard)

# verification = VerificationAgent().run(intent, storyboard)
# print(verification)




path = RenderingAgent().run(str(uuid.uuid4()), 'corporate', 'corporate')
print('PPTX saved to:', path)

