#!/usr/bin/env python3
"""Reuse Lab3's real serial VM acceptance without overwriting Lab3 evidence."""
import check_lab3_runtime

if __name__ == '__main__':
    check_lab3_runtime.main('labs/lab4/evidence', 'vm-regression-serial.txt')
