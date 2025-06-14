---
trigger: manual
---

# Rule: Self-Improvement & Knowledge Management Protocol
# Activation: Always On
# Description: Defines the process and constraints for self-improvement, including managing a multi-file rule base and creating/modifying tools.

---
<improvement_hierarchy>
### **Decision-Making Process for Improvement**

When an error is detected, you must follow this hierarchy to propose a solution. Announce which step you are choosing.
1.  **Modify Existing Rule:** Is there an existing rule in ANY `.md` file in the `.windsurf/rules/` directory that can be slightly modified or clarified to fix the error? This is the most preferred option.
2.  **Add to Existing Rule File:** If modification isn't enough, can the new learning be appended to an existing, relevant rules file (like adding a new LEARNING to `extraction_rules.md`)?
3.  **Create New Rule File:** Only if an existing extraction rule file is approaching its character limit, propose creating a new one.
4.  **Modify Existing Tool:** Is the problem better solved by modifying the logic in an existing Python tool?
5.  **Create New Tool:** Only if no existing tool's purpose aligns with the required task, propose creating a new one.
</improvement_hierarchy>

---
<rule_management_protocol>
- **Permission:** You may propose to **MODIFY** existing rule files or **CREATE** new ones.
- **Constraints (CHECK FIRST):**
  - **Character Limit:** Any single rule file CANNOT exceed 6000 characters. Before proposing to add to a file, you must check its size with `wc -c .windsurf/rules/path/to/rule.md`.
  - **File Count Limit:** A maximum of 5 rule files total is permitted. Check with `ls .windsurf/rules/*.md | wc -l`.
- **Process for Creating a New Extraction Rule File:**
  - **Trigger:** This action is only permitted if the most relevant existing `extraction_rules...md` file is over **5800 characters** AND the total rule file count is less than 5.
  - **Action:**
    1. Announce that the primary rule file is full and a new supplement is needed.
    2. Determine the next available number (e.g., if `extraction_rules_supplement_1.md` exists, propose `extraction_rules_supplement_2.md`).
    3. Propose the new, correctly named file.
    4. Provide the complete content for the new file, starting with a clear header (e.g., `# Rule: M&A Data Extraction - Supplement 1`).
- **Always await user confirmation** before writing or modifying any file. For modifications, provide a `diff`.
</rule_management_protocol>

---
<tool_management_protocol>
- **Permission:** You may propose to **CREATE** new Python tools (`/tools`) & MCP servers OR **MODIFY** existing ones.
- **Trigger:** Propose a tool action for complex, deterministic, or repetitive tasks unfit for rules. A modification is preferred over creating a new tool if the functionality is related.
- **Constraints (CHECK FIRST):**
  - **Creation:** Max 7 Python tools & 7 MCP servers.
  - **Modification/Creation:** Any Python tool file CANNOT exceed 500 lines of code (LOC). Check with `wc -l tools/path/to/script.py`.
- **Process:**
  - **For Creation:** State purpose, provide complete code/config, and explain integration.
  - **For Modification:** State filename, reason, and provide changes in a `diff` format.
- **Always await user confirmation** before creating or modifying any file.
</tool_management_protocol>