import time
from ollama import chat
from app.models.task import PlannerOutput

for i in range(2):
    start = time.time()
    response = chat(
        model="qwen3:4b",
        messages=[{
            "role": "user",
            "content": (
                "Break this goal into exactly 3 to 5 tasks: Build a login page. "
                "Keep each description under 20 words."
            )
        }],
        format=PlannerOutput.model_json_schema(),
        think=False,
    )
    print(f"Run {i+1} took {time.time() - start:.1f}s")
    print(response.message.content)
    print("---")