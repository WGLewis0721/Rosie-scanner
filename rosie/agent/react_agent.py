import logging
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from ..llm.backend import get_llm
from .tools import TOOLS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Rosie, an AI assistant that helps engineers understand their AWS environment.
You have access to tools that query the AWS inventory. Use them to answer questions accurately.
Always provide resource IDs and relevant context in your answers.
You can analyze network configurations including VPCs (ec2:vpc), subnets (ec2:subnet), security groups (ec2:security_group), NACLs (ec2:nacl), route tables (ec2:route_table), internet gateways (ec2:internet_gateway), NAT gateways (ec2:nat_gateway), Transit Gateways (ec2:transit_gateway), TGW attachments (ec2:tgw_attachment), VPC peering connections (ec2:vpc_peering), and VPC endpoints (ec2:vpc_endpoint).

Tools available:
{tools}

Use the following format:
Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Question: {input}
Thought: {agent_scratchpad}"""

def build_agent(provider: str | None = None, model: str | None = None) -> AgentExecutor:
    llm = get_llm(provider=provider, model=model)
    prompt = PromptTemplate.from_template(SYSTEM_PROMPT)
    agent = create_react_agent(llm, TOOLS, prompt)
    return AgentExecutor(agent=agent, tools=TOOLS, verbose=True, handle_parsing_errors=True)

def ask(question: str, provider: str | None = None, model: str | None = None) -> str:
    executor = build_agent(provider=provider, model=model)
    try:
        result = executor.invoke({"input": question})
        return result.get("output", "No answer generated.")
    except Exception as e:
        logger.error(f"Agent error: {e}")
        return f"Error: {e}"
