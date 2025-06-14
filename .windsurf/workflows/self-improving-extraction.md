---
description: Workflow to self improve agent information extraction accuracy from txt files
---

# Title: Self-Improving M&A Data Extractor with Attention Guiding
## Description: Extracts raw data by first pre-processing to locate keywords, then using those locations to guide extraction. It evaluates against a golden set and refines its multi-file rule base or its tools to improve accuracy.

---
### PHASE 1: PRE-PROCESSING & ATTENTION GUIDING

1.  **Acknowledge Goal & Load Knowledge:** I will iterate through `/golden_data` to pre-process text. I will first load my entire knowledge base.
2.  **Load All Rules:** Use `ls .windsurf/rules/*.md` to identify all available rule files. You must consider the contents of **ALL** these files, especially `self_improvement_protocol.md`, for every decision.
3.  Create temp dir: `mkdir -p temp`.
4.  For EACH project folder in `golden_data`, perform pre-processing:
    a. `PROJECT_NAME` = current folder name.
    b. Aggregate Text: `cat golden_data/${PROJECT_NAME}/*.txt > temp/${PROJECT_NAME}_aggregated.txt`.
    c. Analyze Keywords: `python tools/keyword_finder.py temp/${PROJECT_NAME}_aggregated.txt`. This creates a `.locations.json` file.

---
### PHASE 2: THE GUIDED TRAINING LOOP

5.  Announce pre-processing complete, starting main guided training loop.
6.  For EACH project folder in `golden_data`, perform the main loop:
    a. `PROJECT_NAME` = current folder name. Announce.
    b. **Guided Extraction:**
        i. Read text: `temp/${PROJECT_NAME}_aggregated.txt`. Read hints: `temp/${PROJECT_NAME}_aggregated.locations.json`.
        ii. Task: Apply all loaded rules. Use hints to guide search. Extract raw data with justifications.
        iii. Save output to `extracted_output/${PROJECT_NAME}_extracted.json`.
    c. **Evaluation:**
        i. Define paths: `GENERATED_FILE` and `GOLDEN_FILE`.
        ii. Run evaluator: `python tools/evaluator.py ${GENERATED_FILE} ${GOLDEN_FILE}`.
        iii. Review the full output, including SCORE and ERRORS.
    d. **Self-Refinement:**
        i. Analyze SCORE and ERRORS. If perfect, continue to the next project.
        ii. If NOT perfect, perform root cause analysis. Consult the `<improvement_hierarchy>` in `self_improvement_protocol.md` to decide on the best path.
        iii. **Execute Improvement Path:**
            *   **Path A (Manage Rules):** Follow the `<rule_management_protocol>`. Propose to modify or create a rule file after checking all constraints (char count, file count).
            *   **Path B (Manage Tools):** Follow the `<tool_management_protocol>`. Propose to modify or create a tool after checking all constraints (tool count, LOC).
            *   **Fallback:** If any constraint prevents your proposed action, announce this and attempt a solution using a different path.
            *   **Await user confirmation** before any file write or modification.
        iv. **Verification:** After a change is approved, re-run extraction and evaluation on the SAME project (repeat steps 6.b, 6.c, and 6.d) until the score is perfect.

---
### PHASE 3: FINAL REPORT & CLEANUP

7.  After all projects are processed, provide a final summary report listing all rule and tool modifications/creations.
8.  Cleanup: `rm -rf temp`.
9.  Announce training is complete.