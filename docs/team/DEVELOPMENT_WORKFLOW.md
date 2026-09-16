# Development & Git Workflow

## Branch Hierarchy

```
main
  ↓
develop
  ↓
feature/*
fix/*
docs/*
```

> [!CAUTION]
> **NEVER push directly to `main`.**
> All code must go through a feature branch and merge into `develop` via a Pull Request. Only stable, tested versions from `develop` are tagged into `main`.

---

## Step-by-Step Developer Workflow

### 1. Before Starting Work
Always pull the latest changes from `develop`:
```bash
git checkout develop
git pull origin develop
git checkout -b feature/<name>
```

### 2. During & After Development
Commit frequently with conventional commit messages:
```bash
git add .
git commit -m "feat: <description>"
git push origin feature/<name>
```

### 3. Merging via Pull Request
```
Create Pull Request (targeting develop)
       ↓
Code Review
       ↓
Automated Tests (Pytest + Next.js build)
       ↓
Merge into develop
```

---

## Commit Conventions

Use standard Conventional Commit prefixes:

- `feat:` A new functional feature or capability
- `fix:` A bug fix or defect correction
- `docs:` Documentation-only changes
- `test:` Adding or refactoring tests
- `refactor:` Code improvements without behavioral changes
- `chore:` Dependency, build, or configuration updates

### Examples:
- `feat: add tender upload API`
- `feat: implement requirement extraction`
- `fix: handle scanned PDF`
- `test: add turnover validation tests`
- `docs: update demo flow`

---

## Pull Request Rules

Every PR must be opened using `.github/pull_request_template.md` and contain:

- **What changed**: Clear summary of code additions/modifications.
- **Why**: The problem solved or requirement fulfilled.
- **Testing performed**: Exact commands or manual verification executed.
- **Screenshots/demo**: Visual proof if UI changes were made.
- **Related issue**: Issue number being closed or addressed.
- **Security confirmation**: Explicit check that no API keys, secrets, or `.env` files were committed.
