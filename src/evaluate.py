import argparse
import json
from medrag import AgenticMedRAG
import os
import re
import traceback

dataset_names = ['mmlu', 'medqa', 'medmcqa', 'pubmedqa', 'bioasq']


if __name__ == "__main__":
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm_name", type=str, default="qwen/Qwen3-4B")
    parser.add_argument("--dataset_name", type=str, default="mmlu", choices=dataset_names)
    parser.add_argument("--results_dir", type=str, default="prediction")
    parser.add_argument("--m", type=int, default=None)
    parser.add_argument("--n", type=int, default=None)
    parser.add_argument("--agents", action="store_true", help="Whether to use the agentic version of MedRAG") 
    args = parser.parse_args()

    llm_name = args.llm_name
    dataset_name = args.dataset_name
    results_dir = args.results_dir
    agents = args.agents
    n = args.n
    m = args.m
    
    folder_name = f"{llm_name}"
    safe_folder_name = re.sub(r'[<>:"/\\|?*]', '-', folder_name.lower())
    if agents:
        safe_folder_name = f"{safe_folder_name}-agents"
    dir = os.path.join(results_dir, safe_folder_name)
    os.makedirs(dir, exist_ok=True)

    medrag = AgenticMedRAG(llm_name=llm_name, agents=agents)
    
    benchmark = json.load(open(os.path.join(".", "src", "benchmark.json")))
    dataset = benchmark[dataset_name]
    keys = list(dataset.keys())
    keys = keys[m:n]
    subset = {}
    subset[dataset_name] = {qid: dataset[qid] for qid in keys}
    
    with open(os.path.join(dir, f"{dataset_name}.txt"), 'a') as f:

        for qid, qdata in subset[dataset_name].items():
            question = qdata["question"]
            options = qdata["options"]
            true_answer = qdata["answer"]
            
            error_type = ""
            error_traceback = ""
            result = {"answer_choice": None, "justification": None}
            
            # result, callback = medrag.answer(question=question, options=options)
            # print(result)

            try:
                result, callback = medrag.answer(question=question, options=options)
                
            except Exception as e:
                error_type = f"Exception: {repr(e)}"
                error_traceback = traceback.format_exc()
            
            result_log = {
                "qid": f"{dataset_name}/{qid}",
                "question": question,
                "options": options,
                "true_answer": true_answer,
                "answer_choice": result.get("answer_choice", None),
                "justification": result.get("justification", None),
                "queries": str(result.get("queries", [])),
                "literature": result.get("literature", []),
                "hypotheses": str(result.get("hypotheses", None)),
                "knowledge_cache": result.get("knowledge_cache", []),
                "comments": result.get("comments", None),
                "is_correct": (result.get("answer_choice", None) == true_answer),
                "error_type": error_type[:100]+error_type[-200:],
                "error_traceback": error_traceback[:100]+error_traceback[-200:],
            }

            f.write(json.dumps(result_log,) + "\n")
                        
            f.flush()
            os.fsync(f.fileno())