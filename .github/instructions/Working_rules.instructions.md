# Working Rules and Instructions

## General Principles

### Code Quality
- Write clean, maintainable code
- Follow existing code conventions and patterns
- Ensure comprehensive error handling
- Add meaningful comments where necessary
- Keep functions focused and single-purpose

### Testing
- Write tests for new functionality
- Ensure existing tests continue to pass
- Test edge cases and error conditions
- Perform integration testing

### Documentation
- Document all public APIs
- Keep README files up to date
- Add inline comments for complex logic
- Maintain changelog

### Version Control
- Make atomic commits with clear messages
- Keep commits focused on single changes
- Review changes before committing
- Don't commit sensitive information

## Repository-Specific Rules

### OmniFlow Beta Conventions

#### Code Style
- Follow Python PEP 8 style guide
- Use type hints where appropriate
- Keep line length reasonable
- Use meaningful variable names

#### File Organization
- Place Azure Functions in appropriate directories
- Keep shared utilities in `/backend/shared/`
- Organize tools in `/backend/tools/`
- Maintain consistent directory structure

#### Error Handling
- Use try-except blocks appropriately
- Log errors with proper context
- Return meaningful error messages
- Handle edge cases gracefully

#### Logging
- Use structured logging
- Include relevant context in log messages
- Use appropriate log levels
- Don't log sensitive information

### Best Practices from Related Repositories

#### From OmniFlowCentral
- Implement robust database search patterns
- Use comprehensive error handling
- Maintain clean separation of concerns
- Implement thorough logging

#### From CV Generator
- Use clear and effective prompting
- Design user-friendly interactions
- Provide informative responses
- Focus on user experience

## Development Workflow

### Before Starting
1. Understand the requirements fully
2. Analyze existing code and patterns
3. Create a solid implementation plan
4. Review plan with team if needed

### During Development
1. Make small, incremental changes
2. Test frequently
3. Keep code clean and readable
4. Document as you go

### Before Committing
1. Review all changes
2. Run tests
3. Check for any debugging code or comments
4. Ensure no sensitive data is included
5. Verify commit message is clear

### Code Review
- Be open to feedback
- Explain your design decisions
- Address all review comments
- Update documentation as needed

## Security Guidelines

### Sensitive Data
- Never commit credentials or API keys
- Use environment variables for secrets
- Don't log sensitive information
- Sanitize user input

### Best Practices
- Validate all inputs
- Use parameterized queries
- Implement proper authentication
- Follow principle of least privilege

## Communication

### Commit Messages
- Use clear, descriptive messages
- Follow conventional commit format if applicable
- Reference issues or tickets when relevant
- Keep first line under 50 characters

### Documentation
- Write for your audience
- Include examples
- Keep it up to date
- Be clear and concise

## Quality Assurance

### Before Finalizing
- [ ] All tests pass
- [ ] Code follows style guidelines
- [ ] Documentation is complete
- [ ] No security issues
- [ ] Error handling is comprehensive
- [ ] Logging is appropriate
- [ ] No regressions introduced
- [ ] Changes are minimal and focused

## Important Reminders

1. **Plan Before Implementing**: Always create a solid plan before writing code
2. **Follow Existing Patterns**: Stay consistent with the existing codebase
3. **Test Thoroughly**: Don't skip testing
4. **Document Well**: Future you will thank present you
5. **Security First**: Never compromise on security
6. **Quality Over Speed**: Take time to do it right
7. **Ask When Unsure**: Better to ask than to assume

## Repository Maintenance

### Regular Tasks
- Keep dependencies updated
- Review and update documentation
- Clean up deprecated code
- Monitor for security vulnerabilities
- Review and improve test coverage

### Long-term Goals
- Maintain high code quality
- Keep technical debt manageable
- Improve performance where possible
- Enhance user experience
- Stay current with best practices
