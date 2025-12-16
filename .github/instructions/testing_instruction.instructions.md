---
applyTo: '**'
---
Focus on discovering the essential knowledge that would help an AI agents be immediately productive in this testing. Consider aspects like:
- The "big picture" architecture that requires reading multiple files to understand - major components, service boundaries, data flows, and the "why" behind structural decisions
- Critical developer workflows (builds, tests, debugging) especially commands that aren't obvious from file inspection alone
- Project-specific conventions and patterns that differ from common practices
- Integration points, external dependencies, and cross-component communication patterns
you develop testing code for both backend and frontend parts of the project. Ensure that the tests cover all new features and bug fixes. Write unit tests for individual functions as well as integration tests to verify end-to-end functionality. Use appropriate testing frameworks for Azure Functions and Streamlit applications. Document the testing procedures and how to run the tests in the project documentation.
When writing tests, consider edge cases and potential failure points. Ensure that the tests validate not only expected outcomes but also handle unexpected inputs gracefully. Use mock data and services where necessary to isolate components during testing.
After implementing tests, run them to verify that all functionalities work as intended. If any tests fail, debug the issues and make necessary code adjustments until all tests pass successfully.
In case of bigger issues consult with users or team members to get insights and solutions.
always save scripts in appropriate test files in backend/tests/ or frontend/tests/ directories.
if u see any test file out of right directory move them to correct place.
