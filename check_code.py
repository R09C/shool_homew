import requests
import os
import re
import json
from typing import Optional, List, Dict, Any


USE_MOCK_LLM = True


API_TOKEN = os.getenv("HF_TOKEN")
MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
API_URL = f"https://api-inference.huggingface.co/models/{MODEL_ID}"
HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}


def get_code_similarity(source_code: str, code_to_compare: str) -> Optional[float]:
    """Вычисляет косинусное сходство между двумя фрагментами кода."""
    print("-> Запрос косинусного сходства через Hugging Face API...")
    payload = {
        "inputs": {"source_sentence": source_code, "sentences": [code_to_compare]},
        "options": {"wait_for_model": True},
    }
    try:
        response = requests.post(API_URL, headers=HEADERS, json=payload, timeout=20)
        response.raise_for_status()
        similarity_scores = response.json()
        print("<- Ответ от Hugging Face API получен.")
        return similarity_scores[0] if similarity_scores else None
    except requests.exceptions.RequestException as e:
        print(f"!! Ошибка API Hugging Face: {e}")
        return None


def get_llm_code_review(submitted_code: str, algorithm_name: str) -> str:
    """
    Отправляет код на оценку LLM с учетом контекста (названия алгоритма).
    """
    try:
        from g4f.client import Client
        from g4f.models import DeepInfraChat
    except ImportError:
        print(
            "!! Библиотека g4f не установлена. Пожалуйста, установите: pip install g4f"
        )
        return ""

    print("-> Отправка кода на ревью в LLM с улучшенным промптом...")

    client = Client()

    prompt = f"""
    Ты — опытный тимлид, который проводит код-ревью. Проанализируй следующий код на Python.

    **ВАЖНЫЕ ПРАВИЛА ОЦЕНКИ:**
    1.  **Контекст алгоритма:** Код реализует алгоритм с названием "{algorithm_name}". Оценивай **правильность реализации ИМЕННО ЭТОГО алгоритма**. Если "{algorithm_name}" реализован верно, оценка за **Правильность** должна быть 5/5, даже если сам алгоритм неоптимален. Оценку за **Оптимальность** ставь, сравнивая сложность реализованного алгоритма с эталонной сложностью для "{algorithm_name}".
    2.  **Комментарии:** Не снижай оценку за наличие, отсутствие или стиль комментариев. Это не является ошибкой.
    3.  **Стиль:** Оценивай только читаемость кода.

    **ЗАДАЧА:**
    Оцени код по трем критериям: Правильность, Оптимальность, Стиль.
    Твой ответ должен быть СТРОГО в следующем формате JSON, без лишних слов:
    {{
      "Правильность": {{ "grade": <оценка от 1 до 5>, "comment": "<обоснование>" }},
      "Оптимальность": {{ "grade": <оценка от 1 до 5>, "comment": "<обоснование>" }},
      "Стиль": {{ "grade": <оценка от 1 до 5>, "comment": "<обоснование>" }}
    }}

    **Код для анализа:**
    ---
    {submitted_code}
    ---
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-prover-v2-671b",
            messages=[{"role": "user", "content": prompt}],
            provider=DeepInfraChat,
        )
        review_text = response.choices[0].message.content
        print("<- Ответ от LLM получен.")
        return review_text
    except Exception as e:
        print(f"!! Ошибка при вызове LLM: {e}")
        return ""


def parse_llm_review_json(review_text: str) -> Dict[str, Any]:
    """Извлекает оценки и комментарии из JSON-ответа LLM."""
    try:

        match = re.search(r"\{.*\}", review_text, re.DOTALL)
        if match:
            json_str = match.group(0)
            return json.loads(json_str)
        else:
            raise ValueError("JSON не найден в ответе LLM")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"!! Ошибка парсинга JSON от LLM: {e}")
        return {
            "Правильность": {"grade": 0, "comment": "Ошибка парсинга ответа LLM."},
            "Оптимальность": {"grade": 0, "comment": "Ошибка парсинга ответа LLM."},
            "Стиль": {"grade": 0, "comment": "Ошибка парсинга ответа LLM."},
        }


def perform_comprehensive_evaluation(
    template_code: str, submitted_code: str, algorithm_name: str
) -> Dict[str, Any]:
    """
    Выполняет комплексную оценку кода, объединяя количественные и качественные метрики.
    """
    print("\n" + "=" * 60)
    print(f"НАЧАЛО ОЦЕНКИ АЛГОРИТМА: '{algorithm_name.upper()}'")
    print("=" * 60)

    final_report = {}

    similarity = get_code_similarity(template_code, submitted_code)
    originality_report = {
        "grade": 0,
        "comment": "Оценка не проводилась.",
        "similarity": "N/A",
    }
    if similarity is not None:
        originality_report["similarity"] = f"{similarity:.4f}"
        if similarity > 0.95:
            originality_report["grade"] = 1
            originality_report["comment"] = (
                "Код практически идентичен шаблону (плагиат)."
            )
        elif similarity > 0.8:
            originality_report["grade"] = 2
            originality_report["comment"] = (
                "Очень высокое сходство, вероятно, простое переименование."
            )
        else:
            originality_report["grade"] = 5
            originality_report["comment"] = "Код достаточно оригинален по структуре."
    final_report["Оригинальность (Анти-плагиат)"] = originality_report

    llm_review_text = get_llm_code_review(submitted_code, algorithm_name)

    parsed_llm_review = parse_llm_review_json(llm_review_text)
    final_report.update(parsed_llm_review)
    sred_grade = sum(item.get("grade", 0) for item in final_report.values()) / len(
    final_report
    )
    print(final_report)

    return sred_grade, final_report["Правильность"]["grade"]


if __name__ == "__main__":
    if not API_TOKEN or "hf_xxx" in API_TOKEN or len(API_TOKEN) < 20:
        print("\n!! ОШИБКА: API токен Hugging Face не найден или некорректен.")
    else:

        ALGORITHM_NAME = "Bubble Sort"

        template_code = """
        def bubble_sort_classic(arr):
            n = len(arr)
            for i in range(n):
                for j in range(0, n - i - 1):
                    if arr[j] > arr[j + 1]:
                        arr[j], arr[j + 1] = arr[j + 1], arr[j]
        """

        submitted_code = """
        
        def q(data):
            size = len(data)
            
            for k in range(size):
                
                for l in range(0, size - k - 1):
                    if data[l] > data[l + 1]:
                        
                        data[l], data[l + 1] = data[l + 1], data[l]
        """

        grade = perform_comprehensive_evaluation(
            template_code=template_code,
            submitted_code=submitted_code,
            algorithm_name=ALGORITHM_NAME,
        )
        print(grade)
