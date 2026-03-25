import argparse
from collections import Counter, defaultdict
import json
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import PydanticOutputParser
from transformers import AutoTokenizer
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.callbacks import get_openai_callback
from langchain_core.messages import AIMessage
from pydantic import  BaseModel, Field
import math
import operator
import os
import re
import sys
sys.path.append("src")
from template_dfa import *
from typing import Any, Annotated, Callable, Dict, List, Literal, Optional, Tuple, TypedDict, Iterable
from utils import RetrievalSystem

def strip_think(msg: AIMessage) -> AIMessage:
    msg.content = re.sub(r"<think>.*?</think>\s*", "", msg.content, flags=re.DOTALL).strip()
    return msg.model_copy(update={"content": msg.content})

class GeneralOutput(BaseModel):
    answer_choice: str
    justification: str

class Query(BaseModel):
    text: str
    justification: str
    
class PlannerOutput(BaseModel):
    queries: List[Query] = Field(default_factory=list,)
    
class Finding(BaseModel):
    text: str
    justification: str
    source: str
    
class DigesterOutput(BaseModel):
    findings: List[Finding] = Field(default_factory=list, description="Findings derived from the retrieved documents.")

class Premise(BaseModel):
    text: str = Field(..., description="Format: [Subject] + [Predicate] + [Object] + [Adjuncts]")
    source: Literal["stem", "question", "options", "literature", "knowledge cache", "prior conclusion", "medical knowledge"]

class Hypothesis(BaseModel):
    premises: List[Premise] = Field(default_factory=list,)
    conclusion: str = Field(..., description="Format: [Subject] + [Predicate] + [Object] + [Adjuncts]")
        
class CompilerOutput(BaseModel):
    hypotheses: List[Hypothesis] = Field(default_factory=list,)
    
class Knowledge(BaseModel):
    text: str
    verified: Literal["true", "false", "mixed"] = "false"
    rationale: str
    
class FixerOutput(BaseModel):
    hypotheses: List[Hypothesis] = Field(default_factory=list,)
        
class ExaminerOutput(BaseModel):
    comment: str
    require_fixing: bool = False
    
class EvaluatorOutput(BaseModel):
    answer_choice: str
    justification: str

class GraphState(TypedDict):
    question: str
    options: Dict[str, str]
    answer_choice: str
    justification: str
    queries: List[Any]
    literature: str
    hypotheses: List[Any]
    knowledge_cache: List[Any]
    comments: Dict[str, Any]
    require_fixing: bool
    max_retries: int
    retries: Counter[str]
    step: int

general_prompt = ChatPromptTemplate.from_messages([
    ("system", general_system),
    ("user", general_user)
])

planner_prompt = ChatPromptTemplate.from_messages([
    ("system", planner_system),
    ("user", planner_user)
])

digester_prompt = ChatPromptTemplate.from_messages([
    ("system", digester_system),
    ("user", digester_user)
])

compiler_prompt = ChatPromptTemplate.from_messages([
    ("system", compiler_system),
    ("user", compiler_user)
])

factchecker_prompt = ChatPromptTemplate.from_messages([
    ("system", factchecker_system),
    ("user", factchecker_user)
])

fixer_prompt = ChatPromptTemplate.from_messages([
    ("system", fixer_system),
    ("user", fixer_user)
])

examiner_prompt = ChatPromptTemplate.from_messages([
    ("system", examiner_system),
    ("user", examiner_user)
])

evaluator_prompt = ChatPromptTemplate.from_messages([
    ("system", evaluator_system),
    ("user", evaluator_user)
])

general_parser = PydanticOutputParser(pydantic_object=GeneralOutput)
planner_parser = PydanticOutputParser(pydantic_object=PlannerOutput)
digester_parser = PydanticOutputParser(pydantic_object=DigesterOutput)
compiler_parser = PydanticOutputParser(pydantic_object=CompilerOutput)
factchecker_parser = PydanticOutputParser(pydantic_object=Knowledge)
fixer_parser = PydanticOutputParser(pydantic_object=FixerOutput)
examiner_parser = PydanticOutputParser(pydantic_object=ExaminerOutput)
evaluator_parser = PydanticOutputParser(pydantic_object=EvaluatorOutput)

def retrieve_context(
    retrieval_system: RetrievalSystem,
    tokenizer: Any,
    context_length: Optional[int],
    query: str,
    k: int = 32,
    rrf_k: int = 100,
):
    assert retrieval_system is not None
    assert tokenizer is not None
    
    snippets, scores = retrieval_system.retrieve(query, k=k, rrf_k=rrf_k )
    context = "\n".join(["Document [{:d}] (Title: {:s}) {:s}".format(idx, snippet["title"], snippet["content"]) for idx, snippet in enumerate(snippets)])
    token_ids = tokenizer.encode(
        context,
        add_special_tokens=False,
        truncation=False,
    )
    token_ids = token_ids[:context_length]
    # print(f"Total tokens after truncation: {len(token_ids)}")
    snippets = tokenizer.decode(
        token_ids,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )
    return snippets, scores

def create_general_node(chain, retrieve_context):
    def node(state: GraphState) -> GraphState:
        context, _ = retrieve_context(
            query=state["question"],
            k = 16,
        )
        result = chain.invoke({
            "question": state["question"],
            "options": state["options"],
            "context": context,
            "format_instructions": general_parser.get_format_instructions(),
        })
        return {
            **state,
            "answer_choice": result.answer_choice,
            "justification": result.justification,
        }
    return node

def create_planner_node(chain):
    def node(state: GraphState) -> GraphState:
        try:
            result = chain.invoke({
                "question": state["question"],
                "options": state["options"],
                "format_instructions": planner_parser.get_format_instructions(),
            })
            queries = result.queries
        except:
            queries = []
        return {
            **state,
            "queries": queries,
            "require_fixing": False,
            "step": 0,
            "comments": defaultdict(list),
            "knowledge_cache": [],
            "retries": Counter(),
            "max_retries": 0
        }
    return node

def create_digester_node(chain, retrieve_context):
    def node(state: GraphState) -> GraphState:
        results = ""
        for q in state["queries"]:
            snippets, _ = retrieve_context(query=q.text, k=3)
            try:
                result = chain.invoke({
                    "query": q.text,
                    "retrieved_documents": snippets,
                    "format_instructions": digester_parser.get_format_instructions(),
                })
                results += "Results for {:s}:\n".format(q.text)
                results += "\n".join([finding.json() for finding in result.findings]) + "\n"
            except:
                results = None
        return {
            **state,
            "literature": results,
        }
    return node

def create_compiler_node(chain):
    def node(state: GraphState) -> GraphState:
        result = chain.invoke({
            "question": state["question"],
            "options": state["options"],
            "literature": state.get("literature", []),
            "format_instructions": compiler_parser.get_format_instructions(),
        })
        return {
            **state,
            "hypotheses": result.hypotheses,
            "max_retries": 2
        }
    return node

def create_examiner_node(chain, helper_chain, retrieve_context):
    def node(state: GraphState) -> GraphState:
        hypotheses = state["hypotheses"]
        question = state["question"]
        options = state["options"]
        literature = state["literature"]
        context = []
        for i, hypothesis in enumerate(hypotheses):
            if state["retries"][i] >= state["max_retries"]: continue
            if state["step"] <= i:
                state["step"] = i
                premises = [premise for premise in hypothesis.premises if premise.source == "medical knowledge"]
                for premise in premises:
                    snippets, _ = retrieve_context(query=premise.text, k=3)
                    helper_result = helper_chain.invoke({
                        "statement": premise.text,
                        "retrieved_documents": snippets,
                        "format_instructions": factchecker_parser.get_format_instructions(),
                    })
                    state["knowledge_cache"] += [helper_result.json()]
                try:
                    result = chain.invoke({
                        "hypothesis": hypothesis.json(),
                        "question": question,
                        "options": options,
                        "context": context,
                        "knowledge_cache": state["knowledge_cache"],
                        "literature": literature,
                        "format_instructions": examiner_parser.get_format_instructions(),
                    })
                    state["comments"][i].append(result.comment)
                    state["require_fixing"] = result.require_fixing
                except:
                    state["comments"][i].append("Error occured at Examiner.")
                    state["retries"][i] = state["max_retries"]
            context.append(hypothesis.conclusion)
            if state["require_fixing"]: break
        return state
    return node

def create_fixer_node(chain):
    def node(state: GraphState) -> GraphState:
        state["require_fixing"] = False
        step = state["step"]
        state["retries"][step] += 1
        if state["retries"][step] >= state["max_retries"]:
            state["comments"][step].append("Max retries reached. ")
            return state
        hypotheses = [hypothesis.json() for hypothesis in state["hypotheses"][:step]]
        comments = "\n".join(comment for comment in state["comments"][step])
        try:
            result = chain.invoke({
                "hypotheses": hypotheses,
                "question": state["question"],
                "options": state["options"],
                "comment": comments,
                "knowledge_cache": state["knowledge_cache"],
                "literature": state["literature"],
                "format_instructions": fixer_parser.get_format_instructions(),
            })
            state["hypotheses"] = state["hypotheses"][:step] + result.hypotheses
        except:
            state["comments"][step].append("Error occured at Fixer.")
            state["step"] += 1
        return state
    return node

def create_evaluator_node(chain):
    def node(state: GraphState) -> GraphState:
        # print("[Evaluating]")
        hypotheses = state["hypotheses"]
        content = "".join([
            "[{:d}] {:s}, Annotation: {:s}\n".format(i, hypothesis.json(), state["comments"][i][-1] if state["comments"][i] else "") for i, hypothesis in enumerate(hypotheses)
        ])
        try:
            result = chain.invoke({
                "question": state["question"],
                "options": state["options"],
                "content": content,
                "format_instructions": evaluator_parser.get_format_instructions(),
            })
            state["answer_choice"] = result.answer_choice
            state["justification"] = result.justification
        except:
            state["comments"]["-1"] += ["Error occured at Evaluator"]
        print(state)
        return state
    return node

class AgenticMedRAG:

    def __init__(self, llm_name="qwen/Qwen3-0.6B", retriever_name="BM25", agents=False, corpus_name="Default", db_dir="./corpus", cache_dir=None, corpus_cache=False, HNSW=False):
        self.llm_name = llm_name
        self.retriever_name = retriever_name
        self.agents = agents
        self.corpus_name = corpus_name
        self.db_dir = db_dir
        self.cache_dir = cache_dir
        self.context_length = 8192
        self.llm = ChatOpenAI(
            stream_usage = False,
            temperature = 0.,
            model = self.llm_name,
            base_url = "http://localhost:8000/v1",
            max_retries=1,
            max_tokens = 8192,
            api_key = "EMPTY",
            seed = 42, 
            top_p = 1,
        )     
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.llm_name,
            trust_remote_code=True,
            use_fast=True
        )
        
        self.retrieval_system = RetrievalSystem(self.retriever_name, self.corpus_name, self.db_dir, cache=corpus_cache, HNSW=HNSW)
        self.retrieve_context = lambda query=None, k=None: retrieve_context(self.retrieval_system, self.tokenizer, self.context_length, query, k)
        
        if not self.agents:
            graph = StateGraph(GraphState)
            general_chain = general_prompt | self.llm | strip_think | general_parser
            general_node = create_general_node(general_chain, self.retrieve_context)
            graph.add_node("general", general_node)
            graph.add_edge(START, "general")
            graph.add_edge("general", END)
            self.app = graph.compile()
        
    def answer(self, question: str, options: Dict[str, str]) -> str:
        
        if self.agents:
            
            planner_chain = planner_prompt | self.llm | strip_think | planner_parser
            digester_chain = digester_prompt | self.llm | strip_think | digester_parser
            compiler_chain = compiler_prompt | self.llm | strip_think | compiler_parser
            factchecker_chain = factchecker_prompt | self.llm | strip_think | factchecker_parser
            examiner_chain = examiner_prompt | self.llm | strip_think | examiner_parser
            fixer_chain = fixer_prompt | self.llm | strip_think | fixer_parser
            evaluator_chain = evaluator_prompt | self.llm | strip_think | evaluator_parser
            
            planner_node = create_planner_node(planner_chain)
            digester_node = create_digester_node(digester_chain, self.retrieve_context)
            compiler_node = create_compiler_node(compiler_chain)
            examiner_node = create_examiner_node(examiner_chain, factchecker_chain, self.retrieve_context)
            fixer_node = create_fixer_node(fixer_chain)
            evaluator_node = create_evaluator_node(evaluator_chain)
            
            graph = StateGraph(GraphState)
            
            graph.add_node("planner", planner_node)
            graph.add_node("digester", digester_node)
            graph.add_node("compiler", compiler_node)
            graph.add_node("fixer", fixer_node)
            graph.add_node("examiner", examiner_node)
            graph.add_node("evaluator", evaluator_node)
            
            graph.add_edge(START, "planner")
            graph.add_edge("planner", "digester")
            graph.add_edge("digester", "compiler")
            graph.add_edge("compiler", "examiner")
            graph.add_conditional_edges(
                "examiner",
                lambda state: "fixer" if state["require_fixing"] else "evaluator"
            )
            graph.add_conditional_edges("fixer", lambda state: "examiner")
            graph.add_edge("evaluator", END)
            
            self.app = graph.compile()

        with get_openai_callback() as callback:
            result = self.app.invoke({
                "question": question,
                "options": options,
            })
        return result, callback

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm_name", type=str, default="qwen/Qwen3-4B")
    parser.add_argument("--agents", action="store_true", help="Whether to use the agents version of MedRAG") 
    args = parser.parse_args()

    llm_name = args.llm_name
    agents = args.agents
    medrag = AgenticMedRAG(llm_name=llm_name, agents=agents)
    
    question = "A lesion causing compression of the facial nerve at the stylomastoid foramen will cause ipsilateral"
    options = {
        "A": "paralysis of the facial muscles.",
        "B": "paralysis of the facial muscles and loss of taste.",
        "C": "paralysis of the facial muscles, loss of taste and lacrimation.",
        "D": "paralysis of the facial muscles, loss of taste, lacrimation and decreased salivation."
    }
    
    result, callback = medrag.answer(question=question, options=options)
    print(result)