#!/usr/bin/env python3
"""docx2md.py — 把课程发的 .docx 说明书转成 Markdown。

不依赖 pandoc / python-docx:docx 本质是 zip 包,直接解析 word/document.xml。
支持标题层级、有序/无序列表、表格、加粗、行内换行。

用法:
  python3 tools/docx2md.py <输入.docx> [输出.md]
  # 省略输出路径时,与输入同名同目录,扩展名换成 .md
"""
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def para_text(p, keep_bold=True):
    """把一个段落里的文字拼出来,加粗段落用 ** 包裹。

    keep_bold=False 时忽略加粗:课程文档常整篇设粗,此时 ** 是噪声而非重点。
    """
    out = []
    for r in p.iter(W + "r"):
        rpr = r.find(W + "rPr")
        bold = keep_bold and rpr is not None and rpr.find(W + "b") is not None
        chunk = []
        for node in r:
            tag = node.tag
            if tag == W + "t":
                chunk.append(node.text or "")
            elif tag == W + "tab":
                chunk.append("\t")
            elif tag in (W + "br", W + "cr"):
                chunk.append("\n")
        s = "".join(chunk)
        if not s:
            continue
        # 只在两侧无空白时加粗,免得 ** 贴到空格上失效
        if bold and s.strip():
            lead = s[: len(s) - len(s.lstrip())]
            trail = s[len(s.rstrip()) :]
            out.append(f"{lead}**{s.strip()}**{trail}")
        else:
            out.append(s)
    return "".join(out).strip()


def heading_level(p):
    """从段落样式里判断标题级别,不是标题则返回 0。"""
    ppr = p.find(W + "pPr")
    if ppr is None:
        return 0
    st = ppr.find(W + "pStyle")
    if st is None:
        return 0
    val = st.get(W + "val", "")
    m = re.search(r"(\d+)", val)
    if m and ("eading" in val or "标题" in val or val.isdigit()):
        return min(int(m.group(1)), 6)
    return 0


def list_prefix(p):
    """判断是否列表项。docx 里有序/无序都靠 numPr 标记,无法可靠区分,统一用 - 。"""
    ppr = p.find(W + "pPr")
    if ppr is None:
        return None
    if ppr.find(W + "numPr") is None:
        return None
    ilvl = ppr.find(W + "numPr").find(W + "ilvl")
    depth = int(ilvl.get(W + "val", "0")) if ilvl is not None else 0
    return "  " * depth + "- "


def table_md(tbl, keep_bold=True):
    """把表格转成 Markdown 表格。首行当表头。

    单行单列的表格在课程文档里通常是代码/终端片段的外框,转成围栏代码块。
    """
    raw = []
    for tr in tbl.findall(W + "tr"):
        cells = []
        for tc in tr.findall(W + "tc"):
            parts = [para_text(p, keep_bold) for p in tc.findall(W + "p")]
            cells.append([x for x in parts if x])
        if cells:
            raw.append(cells)
    if not raw:
        return []

    if len(raw) == 1 and len(raw[0]) == 1:
        body = raw[0][0]
        return ["```"] + [re.sub(r"\*\*", "", ln) for ln in body] + ["```"]

    rows = []
    for cells in raw:
        # 单元格内多段用 <br> 连接,避免破坏表格行结构
        rows.append(["<br>".join(c).replace("|", "\\|") or " " for c in cells])
    width = max(len(r) for r in rows)
    rows = [r + [" "] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |",
           "|" + "|".join([" --- "] * width) + "|"]
    for r in rows[1:]:
        out.append("| " + " | ".join(r) + " |")
    return out


def bold_is_noise(body):
    """整篇加粗时,加粗不携带重点信息,应当忽略。

    统计加粗 run 占全部有文字 run 的比例,超过 60% 判为噪声。
    """
    total = bold = 0
    for r in body.iter(W + "r"):
        if not any((n.text or "") for n in r.iter(W + "t")):
            continue
        total += 1
        rpr = r.find(W + "rPr")
        if rpr is not None and rpr.find(W + "b") is not None:
            bold += 1
    return total > 0 and bold / total > 0.6


def convert(src):
    z = zipfile.ZipFile(src)
    root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(W + "body")
    keep_bold = not bold_is_noise(body)

    lines = []
    seen_text = False
    for child in body:
        if child.tag == W + "p":
            txt = para_text(child, keep_bold)
            if txt and not seen_text:
                # 首个非空段落就是文档标题,提为一级标题
                seen_text = True
                lines += ["# " + txt.replace("**", ""), ""]
                continue
            if not txt:
                # 空段落 → 段间空行,但不要连续堆空行
                if lines and lines[-1] != "":
                    lines.append("")
                continue
            lvl = heading_level(child)
            pref = list_prefix(child)
            plain = txt.replace("**", "")
            if lvl:
                lines += ["", "#" * lvl + " " + plain, ""]
            elif pref:
                lines.append(pref + txt)
            elif re.match(r"^[一二三四五六七八九十]+、", plain) and len(plain) < 40:
                # 未用样式但形如 "一、" 的手写章标题
                lines += ["", "## " + plain, ""]
            elif (re.match(r"^\d+(\.\d+)*[.、]\s*\S", plain) and len(plain) < 50
                  and not re.search(r"[/＋+；，]", plain)):
                # 形如 "1. 实验任务" "0. 开始之前" 的手写节标题。
                # 排除含路径分隔符或以顿号/分号收尾的行——那是正文里的编号列表项。
                lines += ["", "### " + plain, ""]
            elif re.match(r"^[•·]\s*", plain):
                # 文档里的项目符号统一成 Markdown 列表
                lines.append("- " + re.sub(r"^[•·]\s*", "", txt))
            elif re.match(r"^材料[一二三四五六]", plain) and len(plain) < 40:
                lines += ["", "#### " + plain, ""]
            else:
                lines += [txt, ""]
        elif child.tag == W + "tbl":
            if lines and lines[-1] != "":
                lines.append("")
            lines += table_md(child, keep_bold) + [""]

    # 收敛连续空行
    out = []
    for ln in lines:
        if ln == "" and out and out[-1] == "":
            continue
        out.append(ln)
    return "\n".join(out).strip() + "\n"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else re.sub(r"\.docx$", ".md", src)
    md = convert(src)
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    print(f"[ok] {src}\n  -> {dst}  ({len(md)} 字符, {md.count(chr(10))} 行)")


if __name__ == "__main__":
    main()
