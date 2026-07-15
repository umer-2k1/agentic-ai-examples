"""
Parallel Coding Agent in LangGraph
----------------------------------
Shape:  read the file FIRST, then fan out 3 independent analyses that
run AT THE SAME TIME, then a master node joins them into one report.

   [read_file] ──┬─> [find_bugs]    ─┐
                 ├─> [research_docs] ─┼──> [write_report]  (master)
                 └─> [check_style]   ─┘

    pip install -r requirements.txt
    # put GROQ_API_KEY=gsk_... in a .env file (free key at console.groq.com)
"""

from typing import TypedDict
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq

load_dotenv()   # reads GROQ_API_KEY from the .env file

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)


class AgentState(TypedDict):
    file_path: str
    code: str          # filled by read_file
    bugs: str          # filled in parallel
    docs: str          # filled in parallel
    style: str         # filled in parallel
    report: str        # filled by master


# ---- Step 1: read the file (runs first, everyone depends on it) ----
def read_file(state: AgentState):
    with open(state["file_path"]) as f:
        return {"code": f.read()}


# ---- Step 2: three independent workers (run in parallel) ----
def find_bugs(state: AgentState):
    resp = llm.invoke(
        "List likely bugs or logic errors in this code. Be brief.\n\n"
        f"{state['code']}"
    )
    return {"bugs": resp.content.strip()}


def research_docs(state: AgentState):
    resp = llm.invoke(
        "Which libraries/APIs does this code use, and what docs should the "
        "author check? Be brief.\n\n"
        f"{state['code']}"
    )
    return {"docs": resp.content.strip()}


def check_style(state: AgentState):
    resp = llm.invoke(
        "Point out style / readability issues (naming, structure). Be brief.\n\n"
        f"{state['code']}"
    )
    return {"style": resp.content.strip()}


# ---- Step 3: master node (waits for all 3, writes final report) ----
def write_report(state: AgentState):
    report = (
        f"# Review of {state['file_path']}\n\n"
        f"## Bugs\n{state['bugs']}\n\n"
        f"## Docs to check\n{state['docs']}\n\n"
        f"## Style\n{state['style']}\n"
    )
    return {"report": report}


graph = StateGraph(AgentState)
graph.add_node("read_file", read_file)
graph.add_node("find_bugs", find_bugs)
graph.add_node("research_docs", research_docs)
graph.add_node("check_style", check_style)
graph.add_node("write_report", write_report)

# read first
graph.add_edge(START, "read_file")

# FAN-OUT: after reading, launch all 3 analyses at once
graph.add_edge("read_file", "find_bugs")
graph.add_edge("read_file", "research_docs")
graph.add_edge("read_file", "check_style")

# FAN-IN: master waits for all 3 before writing the report
graph.add_edge("find_bugs", "write_report")
graph.add_edge("research_docs", "write_report")
graph.add_edge("check_style", "write_report")
graph.add_edge("write_report", END)

app = graph.compile()


def save_graph_png(path="langgraph_parallel_agent.png"):
    """Auto-generate a PNG of the graph from the actual compiled app."""
    png = app.get_graph().draw_mermaid_png()   # needs internet (mermaid.ink)
    with open(path, "wb") as f:
        f.write(png)
    print(f"graph saved -> {path}")


if __name__ == "__main__":
    save_graph_png()                    # regenerates the diagram every run
    result = app.invoke({"file_path": "example.py"})
    print(result["report"])