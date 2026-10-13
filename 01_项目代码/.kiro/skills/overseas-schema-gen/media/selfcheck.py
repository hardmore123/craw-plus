#!/usr/bin/env python3
"""media 分支自检 — 校验 cases.jsonl 格式 + playbook 完整性 + adapter 规范。

用法：python .kiro/skills/overseas-schema-gen/media/selfcheck.py
"""
from __future__ import annotations
import json, os, sys, re

HERE = os.path.dirname(os.path.abspath(__file__))

def check_cases():
    """校验 cases.jsonl 每行格式"""
    path = os.path.join(HERE, "cases.jsonl")
    if not os.path.exists(path):
        return [("cases.jsonl", "文件不存在")]
    
    errors = []
    required = {"code", "entry_url", "date", "verdict", "signals", "solution", "result", "lesson", "playbook"}
    valid_verdicts = {"success", "partial", "needs_human", "needs_handwritten", "blocked"}
    valid_playbooks = {"jsonld_review", "jsonld_product", "jsonld_product_only", "html_fallback", "waf_playwright"}
    
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append((f"cases.jsonl:L{i}", f"JSON解析失败: {e}"))
                continue
            missing = required - set(data.keys())
            if missing:
                errors.append((f"cases.jsonl:L{i}:{data.get('code','?')}", f"缺字段: {missing}"))
            v = data.get("verdict", "")
            if v and v not in valid_verdicts:
                errors.append((f"cases.jsonl:L{i}:{data.get('code','?')}", f"verdict无效: {v}"))
            p = data.get("playbook", "")
            if p and p not in valid_playbooks:
                errors.append((f"cases.jsonl:L{i}:{data.get('code','?')}", f"playbook无效: {p}"))
    return errors

def check_playbooks():
    """校验 playbook 文件存在"""
    expected = ["jsonld_review", "jsonld_product", "jsonld_product_only", "html_fallback", "waf_playwright"]
    errors = []
    for name in expected:
        path = os.path.join(HERE, "playbook", f"{name}.md")
        if not os.path.exists(path):
            errors.append((f"playbook/{name}.md", "文件不存在"))
    readme = os.path.join(HERE, "playbook", "README.md")
    if not os.path.exists(readme):
        errors.append(("playbook/README.md", "文件不存在"))
    return errors

def check_skill_md():
    """校验 SKILL.md 关键内容"""
    path = os.path.join(HERE, "SKILL.md")
    if not os.path.exists(path):
        return [("SKILL.md", "文件不存在")]
    errors = []
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if "MediaAdapter" not in content:
        errors.append(("SKILL.md", "缺 MediaAdapter 基类描述"))
    if "extract_mode" not in content:
        errors.append(("SKILL.md", "缺 extract_mode 模式说明"))
    if "jsonld_review" not in content:
        errors.append(("SKILL.md", "缺 jsonld_review playbook 引用"))
    return errors

def check_reference():
    """校验 reference.md 关键内容"""
    path = os.path.join(HERE, "reference.md")
    if not os.path.exists(path):
        return [("reference.md", "文件不存在")]
    errors = []
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if "德国反序" not in content:
        errors.append(("reference.md", "缺德国评分反序说明"))
    if "rating_scale" not in content:
        errors.append(("reference.md", "缺 rating_scale 说明"))
    return errors

def main():
    print("=== media 分支自检 ===\n")
    all_errors = []
    
    print("  cases.jsonl 格式校验...")
    all_errors.extend(check_cases())
    
    print("  playbook 完整性校验...")
    all_errors.extend(check_playbooks())
    
    print("  SKILL.md 校验...")
    all_errors.extend(check_skill_md())
    
    print("  reference.md 校验...")
    all_errors.extend(check_reference())
    
    if all_errors:
        print(f"\n❌ 发现 {len(all_errors)} 个问题:")
        for loc, msg in all_errors:
            print(f"  {loc}: {msg}")
        sys.exit(1)
    else:
        print("\n✅ 全部通过")
        sys.exit(0)

if __name__ == "__main__":
    main()
