from harness.core.task import TASKS, get_task, select
from harness.core.types import Sample
from harness.tasks import gsm8k, mmlu


def test_registry_contains_builtin_tasks():
    get_task("gsm8k")
    assert {"gsm8k", "mmlu"} <= set(TASKS)


def test_gsm8k_parse_answer_strips_calculator_annotations():
    reasoning, final = gsm8k.parse_answer("She sold 48/2 = <<48/2=24>>24 clips.\n#### 1,072")
    assert reasoning == "She sold 48/2 = 24 clips."
    assert final == "1072"


def test_gsm8k_fewshot_messages():
    shot = gsm8k.row_to_sample({"question": "Q1", "answer": "a <<1+1=2>>2\n#### 2"}, 0, "train")
    task = get_task("gsm8k", n_shot=1)
    task.solver._fewshot = lambda _: [shot]
    msgs = task.solver.build_messages(Sample(id="t", input="Q2", target="3"))
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[1]["content"] == "a 2\nThe answer is 2."
    assert msgs[2]["content"].startswith("Q2")


def test_mmlu_row_to_prompt():
    row = {
        "question": "2+2?",
        "subject": "elementary_mathematics",
        "choices": ["1", "2", "3", "4"],
        "answer": 3,
    }
    s = mmlu.row_to_sample(row, 7, "test")
    assert s.id == "mmlu/test/7"
    assert s.target == "D"
    prompt = mmlu.user_prompt(s)
    assert "about elementary mathematics" in prompt
    assert "D. 4" in prompt


def test_select_is_deterministic_and_order_preserving():
    samples = [Sample(id=str(i), input="", target="") for i in range(100)]
    a = select(samples, 10, seed=0)
    b = select(samples, 10, seed=0)
    assert [s.id for s in a] == [s.id for s in b]
    assert [int(s.id) for s in a] == sorted(int(s.id) for s in a)
    assert select(samples, 10, seed=None) == samples[:10]
    assert select(samples, 1000, seed=0) == samples


def test_task_fingerprints_depend_on_prompt_settings():
    zero = get_task("mmlu", n_shot=0).solver.describe()["fingerprint"]
    five = get_task("mmlu", n_shot=5).solver.describe()["fingerprint"]
    assert zero != five
