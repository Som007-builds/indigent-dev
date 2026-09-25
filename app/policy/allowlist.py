ALLOWED_TOOLS: dict[str, frozenset[str]] = {
    "inspection": frozenset(
        {
            "read_file",
            "ocr_document",
            "search_knowledge_base",
            "retrieve_section",
            "create_docx",
            "create_xlsx",
        }
    ),
    "coding": frozenset(
        {"read_file", "write_file", "create_code", "execute_code", "run_tests"}
    ),
    "pid_analysis": frozenset({"analyze_image", "extract_pid_graph"}),
}

KNOWN_TOOLS = frozenset().union(*ALLOWED_TOOLS.values())
