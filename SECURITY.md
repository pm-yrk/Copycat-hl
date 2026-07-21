
# Security policy

## Supported use

This repository is maintained as an active personal project and portfolio
case study.

## Reporting a security issue

Do not publish suspected credentials or vulnerabilities in a public GitHub
issue. Contact the repository owner privately with:

- the affected file or component;
- steps to reproduce;
- the potential impact;
- any suggested remediation.

## Repository safety rules

The following must never be committed:

- real `.env` files;
- API secrets or access keys;
- Telegram or webhook tokens;
- private keys or seed phrases;
- local SQLite databases;
- runtime logs and diagnostic exports;
- generated snapshot output;
- local backups or persistent state.

Only placeholder values belong in files ending with `.example`.
