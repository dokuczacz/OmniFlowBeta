# Contributing to OmniFlow Beta

Thank you for your interest in contributing to OmniFlow Beta! We welcome contributions from everyone, whether you're fixing bugs, adding features, improving documentation, or reporting issues.

## 🎯 Ways to Contribute

- **Report Bugs**: Found a bug? Open an issue with details
- **Suggest Features**: Have an idea? We'd love to hear it
- **Improve Documentation**: Fix typos, clarify instructions, add examples
- **Submit Code**: Fix bugs or implement features via pull requests
- **Review Code**: Help review open pull requests
- **Test**: Try to break things and report edge cases

## 🐛 Reporting Bugs

Before submitting a bug report:
1. Check if the issue already exists in [Issues](https://github.com/dokuczacz/OmniFlowBeta/issues)
2. Verify the bug exists in the latest version
3. Try to reproduce the bug with minimal steps

**Use the bug report template** and include:
- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version, Azure Functions version)
- Relevant logs or error messages
- Screenshots or code snippets if applicable

## 💡 Suggesting Features

We love new ideas! When suggesting a feature:
1. Check if it's already been suggested in [Issues](https://github.com/dokuczacz/OmniFlowBeta/issues)
2. Explain **what** you want and **why** it's useful
3. Describe potential alternatives you've considered
4. Consider the scope and impact on existing functionality

**Use the feature request template** to structure your suggestion.

## 🔧 Development Setup

### Prerequisites
- Python 3.11+
- Azure Functions Core Tools v4
- Azurite (for local Azure Storage emulation)
- Git

### Local Environment Setup

1. **Fork and clone the repository**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/OmniFlowBeta.git
   cd OmniFlowBeta
   ```

2. **Set up backend**:
   ```bash
   cd backend
   pip install -r requirements.txt
   cp local.settings.template.json local.settings.json
   # Edit local.settings.json if needed
   ```

3. **Set up frontend** (optional):
   ```bash
   cd frontend
   pip install -r requirements.txt
   ```

4. **Start Azurite**:
   ```bash
   azurite
   ```

5. **Run Azure Functions locally**:
   ```bash
   cd backend
   func start
   ```

6. **Run tests**:
   ```bash
   cd backend
   pytest tests/
   ```

## 🔀 Pull Request Process

### Before You Start
1. **Create an issue** first to discuss significant changes
2. **Check existing PRs** to avoid duplicate work
3. **Keep changes focused**: One PR = One feature/fix

### Making Changes

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bug-fix
   ```

2. **Make your changes**:
   - Follow existing code style and conventions
   - Write clear, descriptive commit messages
   - Add tests for new functionality
   - Update documentation as needed

3. **Test your changes**:
   ```bash
   # Run tests
   pytest backend/tests/
   
   # Test manually with curl or Postman
   curl -X POST http://localhost:7071/api/add_new_data \
     -H "Content-Type: application/json" \
     -H "X-User-Id: test_user" \
     -d '{"target_blob_name":"test.json","new_entry":{"id":"1"}}'
   
   # Test with different user IDs to verify isolation
   ```

4. **Commit your changes**:
   ```bash
   git add .
   git commit -m "feat: add new feature"
   # or
   git commit -m "fix: resolve bug in user validation"
   ```

5. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Open a pull request**:
   - Use the PR template
   - Reference related issues
   - Describe what changed and why
   - Provide testing instructions
   - Add screenshots for UI changes

### Commit Message Guidelines

Follow conventional commit format:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `test:` - Adding or updating tests
- `refactor:` - Code refactoring
- `perf:` - Performance improvements
- `chore:` - Build process, dependencies, etc.

**Examples**:
```
feat: add semantic search endpoint
fix: resolve user isolation bug in list_blobs
docs: update API examples in README
test: add integration tests for tool_call_handler
```

## 📝 Code Style Guidelines

### Python Code
- Follow **PEP 8** style guide
- Use **type hints** where appropriate
- Write **docstrings** for functions and classes
- Keep functions **focused and small**
- Use **descriptive variable names**

**Example**:
```python
def add_new_data(
    target_blob_name: str,
    new_entry: dict,
    user_id: str,
    blob_client: BlobServiceClient
) -> dict:
    """
    Add a new entry to a JSON blob file.
    
    Args:
        target_blob_name: Name of the JSON file
        new_entry: Data entry to add
        user_id: User identifier for isolation
        blob_client: Azure Blob Service Client
    
    Returns:
        dict: Result with status and message
    """
    # Implementation
```

### Azure Functions
- Use **function_app.py** for all route definitions
- Keep function handlers **thin** - delegate to shared modules
- Always **validate user context** in every endpoint
- Use **consistent error handling** patterns
- Log important operations for audit trail

### Testing
- Write tests for new features
- Use **pytest** and follow existing test patterns
- Test **user isolation** for multi-user features
- Include **edge cases** and error scenarios
- Use **mocks** for external dependencies (Azure Storage, OpenAI API)

**Example test**:
```python
def test_add_new_data_user_isolation():
    """Verify user isolation in add_new_data endpoint"""
    # Add data for user1
    result1 = add_new_data("test.json", {"id": "1"}, "user1", mock_client)
    
    # Add data for user2
    result2 = add_new_data("test.json", {"id": "2"}, "user2", mock_client)
    
    # Verify user1 cannot see user2's data
    user1_data = read_blob_file("test.json", "user1", mock_client)
    assert {"id": "2"} not in user1_data
```

## 🧪 Testing Guidelines

### Running Tests
```bash
# Run all tests
pytest backend/tests/

# Run specific test file
pytest backend/tests/test_user_manager.py

# Run with coverage
pytest --cov=backend backend/tests/

# Run with verbose output
pytest -v backend/tests/
```

### Writing Tests
- **Unit tests**: Test individual functions in isolation
- **Integration tests**: Test endpoint-to-endpoint flows
- **Security tests**: Verify user isolation, input validation
- **Edge cases**: Empty inputs, special characters, large payloads

## 📚 Documentation

When contributing documentation:
- Keep language **clear and concise**
- Provide **working examples**
- Update **README.md** if adding major features
- Add **inline comments** for complex logic
- Update **API docs** for new endpoints

## 🔐 Security

If you discover a security vulnerability:
1. **DO NOT** open a public issue
2. Email the maintainer directly: dokuczacz@example.com
3. Provide details on the vulnerability and potential impact
4. Allow time for a fix before public disclosure

## 📋 Code Review Process

All submissions require review before merging:
1. **Automated checks**: Tests, linting, CI/CD must pass
2. **Code review**: At least one maintainer approval required
3. **Testing**: Reviewer verifies changes work as described
4. **Documentation**: Ensure docs are updated if needed

Maintainers may request changes. Please:
- Respond to feedback constructively
- Make requested changes or explain why you disagree
- Keep the discussion focused on the code

## 🎉 Recognition

Contributors are recognized in:
- GitHub contributors page
- Release notes for significant contributions
- README.md (for major features)

## 📞 Questions?

- **GitHub Discussions**: For questions and general discussion
- **GitHub Issues**: For bugs and feature requests
- **Email**: dokuczacz@example.com for private inquiries

## 📜 License

By contributing to OmniFlow Beta, you agree that your contributions will be licensed under the Apache-2.0 License.

---

**Thank you for contributing to OmniFlow Beta!** Every contribution, no matter how small, helps make this project better. 🚀
