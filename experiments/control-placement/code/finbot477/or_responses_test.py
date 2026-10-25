import asyncio, json, os, re
from openai import AsyncOpenAI
key = None
for line in open(__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), '..', '..', '.env')):
    m = re.match(r'\s*OPENROUTER_API_KEY\s*=\s*"?([^"\s]+)', line)
    if m: key = m.group(1)
assert key, "no key"
c = AsyncOpenAI(api_key=key, base_url="https://openrouter.ai/api/v1")
tools=[{"type":"function","name":"get_invoice","description":"Get invoice by id",
        "parameters":{"type":"object","properties":{"invoice_id":{"type":"integer"}},"required":["invoice_id"],"additionalProperties":False},"strict":True}]
async def main():
    msgs=[{"role":"system","content":"You are an invoice agent. Use tools."},
          {"role":"user","content":"What is the amount of invoice 7? Use the tool."}]
    r1 = await c.responses.create(model="openai/gpt-4o-mini", input=msgs, tools=tools, max_output_tokens=200, temperature=0)
    calls=[o for o in r1.output if o.type=="function_call"]
    print("step1 output types:", [o.type for o in r1.output], "usage:", getattr(r1,'usage',None) and (r1.usage.input_tokens, r1.usage.output_tokens))
    if not calls: print("NO TOOL CALL"); return
    fc=calls[0]; print("tool call:", fc.name, fc.arguments)
    msgs.append({"type":"function_call","call_id":fc.call_id,"name":fc.name,"arguments":fc.arguments})
    msgs.append({"type":"function_call_output","call_id":fc.call_id,"output":json.dumps({"invoice_id":7,"amount":1450.0})})
    r2 = await c.responses.create(model="openai/gpt-4o-mini", input=msgs, tools=tools, max_output_tokens=200, temperature=0)
    print("step2 text:", r2.output_text[:200], "usage:", (r2.usage.input_tokens, r2.usage.output_tokens))
asyncio.run(main())
