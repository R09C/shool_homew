from g4f.client import Client
from g4f.models import DeepInfraChat

client = Client()
response = client.chat.completions.create(
    model="deepseek-prover-v2-671b",
    messages=[
        {
            "role": "user",
            "content": """
            докажи теорему коши о существовании предела последовательности 
         """,
        }
    ],
    provider=DeepInfraChat,
)
print(response.choices[0].message.content)
