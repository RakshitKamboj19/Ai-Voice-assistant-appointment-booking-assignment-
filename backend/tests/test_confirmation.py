import unittest
from types import SimpleNamespace

from bot import caller_confirmed
from pipecat.processors.aggregators.llm_context import LLMSpecificMessage


def params_with(messages):
    return SimpleNamespace(context=SimpleNamespace(messages=messages))


class CallerConfirmationTests(unittest.TestCase):
    def test_readback_and_latest_affirmation_pass_with_gemini_specific_messages(self):
        messages = [
            {"role": "user", "content": "My phone number is 9191919191."},
            {"role": "assistant", "content": "I have your phone number as 9191919191. Is that correct?"},
            LLMSpecificMessage(llm="google", message={"thought_signature": "opaque"}),
            {"role": "user", "content": "Yes. Yes."},
        ]
        self.assertTrue(caller_confirmed(params_with(messages), "9191919191"))

    def test_affirmation_without_number_readback_is_rejected(self):
        messages = [
            {"role": "assistant", "content": "Ready to book. Is that okay?"},
            LLMSpecificMessage(llm="google", message={"thought_signature": "opaque"}),
            {"role": "user", "content": "Yes."},
        ]
        self.assertFalse(caller_confirmed(params_with(messages), "9191919191"))


if __name__ == "__main__":
    unittest.main()
