"""XML-aware action parsing for OS_V1 agent."""
import json
import re


def xml_to_json(text):
    """Rewrite XML tool calls into fenced JSON."""
    result = []
    last_end = 0
    pos = 0
    while pos < len(text):
        tool_m = re.search(r"([a-zA-Z_]\w*)(<arg_key>)", text[pos:])
        if not tool_m:
            result.append(text[last_end:])
            # 10 Nov live bug (found while wiring the strong free brain —
            # nemotron probe doubled EVERY plain reply): breaking here used
            # to skip setting last_end, so the final `if last_end < len`
            # below appended the text AGAIN — every action executed TWICE
            # in every wave.
            last_end = len(text)
            break
        tool_start = pos + tool_m.start()
        tool_name = tool_m.group(1)
        args_start = tool_start + len(tool_m.group(1))  # after tool name, before <arg_key>
        arg_text = ""
        scan_pos = args_start
        while True:
            ak_m = re.search(r"<arg_key>([^<]*)</arg_key>", text[scan_pos:])
            if not ak_m:
                break
            vk_m = re.search(r"<arg_value>(.*?)</arg_value>",
                             text[scan_pos + ak_m.end():], re.DOTALL)
            if not vk_m:
                break
            arg_text += text[scan_pos + ak_m.start():
                             scan_pos + ak_m.end() + vk_m.end()]
            scan_pos += ak_m.start() + ak_m.end() + vk_m.end()
        pairs = re.findall(
            r"<arg_key>([^<]+)</arg_key><arg_value>(.*?)</arg_value>",
            arg_text, re.DOTALL)
        args = {}
        for k, v in pairs:
            args[k.strip()] = v.strip()
        _d = {"tool": tool_name, "args": args}
        inner = json.dumps(_d, ensure_ascii=False)
        result.append(text[last_end:tool_start])
        result.append("```json\n" + inner + "\n```")
        last_end = scan_pos
        pos = scan_pos
    if last_end < len(text):
        result.append(text[last_end:])
    return "".join(result)


def looks_truncated(reply):
    r = (reply or "").strip()
    if not r:
        return False
    n = xml_to_json(r)
    if re.search(r"```(json)?\s*\{", n):
        return True
    if r.startswith('{"tool"'):
        return True
    return n.count("```") % 2 == 1
