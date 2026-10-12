#!/usr/bin/env python3
"""Run the unchanged course driver with the Lab2 prompt and diskless QEMU args.

Only its hardcoded prompt literals are adapted in memory. The source is never
written. A boot timeout is counted as a failure, unlike the original driver.
All SEND/WAIT/REPEAT/EXPECT and serial logging use the course implementation.
"""
import ast
import pathlib


class Lab2Prompt(ast.NodeTransformer):
    def visit_Constant(self, node):
        if node.value == "$ ":
            return ast.copy_location(ast.Constant("sh> "), node)
        return node

    def visit_Assign(self, node):
        if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "failures" and isinstance(node.value, ast.Constant)
                and node.value.value == 0):
            node.value = ast.IfExp(test=ast.Name(id="ok", ctx=ast.Load()),
                                   body=ast.Constant(0), orelse=ast.Constant(1))
        return self.generic_visit(node)


def main():
    source = pathlib.Path(__file__).resolve().parents[1] / "support/inject_uart.py"
    tree = ast.fix_missing_locations(Lab2Prompt().visit(ast.parse(source.read_text(encoding="utf-8"))))
    namespace = {"__name__": "lab2_course_driver", "__file__": str(source)}
    exec(compile(tree, str(source), "exec"), namespace)
    namespace["QEMU_ARGS"] = ["-machine", "virt", "-bios", "none", "-kernel", "kernel/kernel",
                              "-m", "128M", "-smp", "1", "-nographic"]
    namespace["main"]()


if __name__ == "__main__":
    main()
