# LLM-Driven Multi-Agent Software Architecture Refactoring with Integrated Formal Verification

## Overview
This project implements a multi-agent approach to software architecture refactoring with LLMs and formal verification (MARRVEL).

## Prerequisites

### Required Tools
1. **Wright# Modules for PAT Verifier**
   - Installation guide: [PAT.ADL Repository](https://github.com/cnacha/PAT.ADL/tree/master)
   - This tool is essential for formal verification of architecture designs
2. **Gephi: Knowledge Graph Visulization**
   - Installation guide: [Gephi](https://gephi.org/)

### Python Dependencies
- Python 3.11.9
- Required packages in requirements.txt
    ```bash
    pip install -r requirements.txt
    ```

## Project Structure
```
Multiagent_Refactoring/
├── Baselines/                  # Baselines
│   
├── GRAG_ADL_Syntax/            # Microsoft GraphRAG
│   ├── input/                  # Input raw documentation for Knowlegde Graph Generation
│   ├── output/                 # Generated Knowlegde Graph contents
│   ├── KnowLedgeGraph.gephi    # Knowlegde Graph
│
├── Helpers/                    # Core functions
│   ├── refactoring.py          # MAARVEL core implementation
│   ├── divide_adl.py           # Design partitioning strategy
│
├── Refactoring_data.xlsx       # List of refactoring tasks (ADL files and requirements)
│
└── parallelrun_refactoring.py  # The MAARVEL with Exploration-Selection Strategys
```

## Usage

Run MAARVEL using the parallel execution script:
```bash
python parallelrun_refactoring.py
```

To customize the execution:
- Adjust the number of refactoring tasks by modifying `start_index` and `end_index` in the script
- Change the number of parallel runs by modifying the range in `args_list`

The script generates two output files:
- `Refactoring_Execution_results.xlsx`: All execution results
- `Final_Refactoring_Execution_results.xlsx`: Results with minimal path changes

## Features
- Automated architecture refactoring using LLMs
- Formal verification of refactored designs
- Multi-agent approach for refactoring tasks
- Integration with Wright# architecture description language

