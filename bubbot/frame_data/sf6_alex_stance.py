"""Alex stance follow-up result filter."""


def filter_alex_stance_results(results, *, alex_stance_followup_context, normalize_char_name, normalize_num_cmd_token):
    if not alex_stance_followup_context or not results:
        return results

    filtered_results = []
    for row in results:
        row_char_key = normalize_char_name(row.get("char_name", ""))
        if row_char_key != "alex":
            filtered_results.append(row)
            continue
        row_num_cmd_norm = normalize_num_cmd_token(row.get("numCmd", ""))
        row_cmn_name = str(row.get("cmnName", "")).lower()
        if row_num_cmd_norm.startswith("2pp>") or "stance >" in row_cmn_name:
            filtered_results.append(row)
    return filtered_results or results
