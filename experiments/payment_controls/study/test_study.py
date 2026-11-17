import unittest
from types import SimpleNamespace

from .development import cases, packets, labels
from .enforce import ARMS, registry_decision
from .live import chat_responses


class StudyTests(unittest.TestCase):
    def test_matched_factors(self):
        self.assertEqual(len(ARMS),7)
        for series,n in (("dev",24),("confirmation",12)):
            self.assertEqual(len(labels(series)),n)
        blocks=list(packets())
        self.assertEqual(len(blocks),120)
        for i in range(0,120,5):
            base,direct,structure,summary,masked=[r["input"] for r in blocks[i:i+5]]
            self.assertEqual(base["state"],direct["state"])
            self.assertEqual(base["criteria"],direct["criteria"])
            self.assertEqual(base["question"],structure["question"])
            self.assertEqual({**summary["state"],"unverified_agent_summary":None},
                             {**base["state"],"unverified_agent_summary":None})
            self.assertIn("[unavailable]",masked["state"]["authenticated_sources"])

    def test_typed_registry(self):
        self.assertEqual(registry_decision({})[0],"review")
        for op,observed,required,decision in [("ge",8,8,"allow"),("le",6,5,"block"),("eq",None,"A","review"),
                                              ("contains",["A","B"],"B","allow"),("ge",True,1,"review")]:
            self.assertEqual(registry_decision(dict(trusted_test=dict(op=op,observed=observed,required=required)))[0],decision)


class StreamingAdapter(unittest.IsolatedAsyncioTestCase):
    async def test_preserves_order_and_arguments(self):
        call=SimpleNamespace(type="function_call",name="lookup",call_id="t",arguments='{"id":1}')
        async def create(**params):
            self.assertFalse(params["stream"])
            return SimpleNamespace(output=[SimpleNamespace(type="message",content=[SimpleNamespace(type="output_text",text="ok")]),call])
        adapter=chat_responses(SimpleNamespace(responses=SimpleNamespace(create=create)))
        events=[e async for e in await adapter.responses.create(model="test",stream=True)]
        self.assertEqual(events[0].delta,"ok")
        self.assertIs(events[1].item,call)
