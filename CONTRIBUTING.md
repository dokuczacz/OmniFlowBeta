# Contributing to OmniFlow Beta

Thank you for your interest in contributing to OmniFlow Beta! We welcome contributions from the community, whether it's bug reports, feature requests, documentation improvements, or code contributions.

---

## How to Contribute

### Opening Issues

We use GitHub Issues to track bugs, feature requests, and general questions. Before opening a new issue, please:

1. **Search existing issues** to see if your topic has already been discussed
2. **Use the appropriate issue template**:
   - Bug Report: For reporting bugs or unexpected behavior
   - Feature Request: For proposing new features or enhancements
3. **Provide as much detail as possible** to help us understand and reproduce the issue

### Running Tests Locally with Azurite

To ensure your changes don't break existing functionality, please run the tests locally before submitting a PR.

#### Prerequisites
- Python 3.11 or higher
- Azurite (local Azure Storage emulator)

#### Steps

1. **Install Azurite** (if not already installed):
   ```bash
   npm install -g azurite
   ```

2. **Start Azurite**:
   ```bash
   azurite
   ```
   This will start the blob, queue, and table storage emulators on the default ports.

3. **Install dependencies**:
   ```bash
   cd backend
   pip install -r requirements.txt
   pip install pytest pytest-cov
   ```

4. **Set environment variables**:
   ```bash
   export AZURE_STORAGE_CONNECTION_STRING="UseDevelopmentStorage=true"
   ```

5. **Run tests**:
   ```bash
   pytest --verbose --cov=. --cov-report=term-missing
   ```

Alternatively, you can use the connection string for Azurite with explicit endpoints:
```bash
export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://localhost:10000/devstoreaccount1;QueueEndpoint=http://localhost:10001/devstoreaccount1;TableEndpoint=http://localhost:10002/devstoreaccount1;"
```

### Style & Guidelines

#### Code Style
- **Python**: Follow PEP 8 conventions
- **Naming**: Use descriptive variable and function names
- **Comments**: Add comments for complex logic, but prefer self-documenting code
- **Type Hints**: Use type hints where appropriate (especially for function signatures)

#### Commit Messages
- Use clear, concise commit messages
- Start with a verb in the imperative mood (e.g., "Add", "Fix", "Update", "Remove")
- Reference issue numbers when applicable (e.g., "Fix user isolation bug (#42)")

Example:
```
Add support for batch blob operations

- Implement batch upload endpoint
- Add tests for batch operations
- Update documentation

Closes #123
```

#### Documentation
- Update relevant documentation when adding or changing features
- Ensure code comments are up-to-date
- Add docstrings to new functions and classes

### Branch Naming

Use descriptive branch names that indicate the type of change:

- `feature/your-feature-name` - For new features
- `bugfix/issue-description` - For bug fixes
- `docs/update-description` - For documentation updates
- `chore/task-description` - For maintenance tasks

Example:
```bash
git checkout -b feature/add-semantic-search
```

### Pull Request Process

1. **Fork the repository** and create your branch from `main` or `develop`
2. **Make your changes** and commit them with clear messages
3. **Run tests locally** to ensure everything works
4. **Update documentation** if needed
5. **Open a Pull Request** with a clear description of your changes
6. **Address review feedback** promptly

#### PR Review Checklist

Before submitting a PR, ensure:
- [ ] Tests pass locally with Azurite
- [ ] Code follows the project's style guidelines
- [ ] New features include appropriate tests
- [ ] Documentation is updated (if applicable)
- [ ] Commit messages are clear and descriptive
- [ ] No secrets or sensitive data are committed
- [ ] User isolation and security are maintained

### Code Review

All submissions require review. We use GitHub pull requests for this purpose. Reviewers will check:

- **Functionality**: Does the code work as intended?
- **Tests**: Are there adequate tests for the changes?
- **Security**: Does the code maintain user isolation and security best practices?
- **Style**: Does the code follow project conventions?
- **Documentation**: Are changes properly documented?

---

## Reporting Security Issues

**Do not open public GitHub issues for security vulnerabilities.**

If you discover a security vulnerability, please email the maintainer directly at:

**dokuczacz@example.com**

We will work with you to understand and address the issue promptly. Please include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fixes (if available)

---

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to dokuczacz@example.com.

---

## Getting Help

- **Documentation**: Check the [docs/](docs/) directory for detailed documentation
- **Issues**: Search existing GitHub issues or open a new one
- **Discussions**: Use GitHub Discussions for questions and general topics
- **Contact**: Reach out to dokuczacz@example.com for direct inquiries

---

## Recognition

We appreciate all contributions! Contributors will be recognized in release notes and the project's acknowledgments.

Thank you for helping make OmniFlow Beta better!
