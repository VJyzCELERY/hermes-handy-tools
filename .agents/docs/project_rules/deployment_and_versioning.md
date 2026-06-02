# Deployment and Versioning Guidelines

## Deployment Tags
Use the following naming convention for deployment tagging:
- Format: `service-name-v<version>`.
- Example: `python_library-v1.0.0`.

## Steps to Deploy
1. Tag the release branch with the appropriate version.
2. Push tags to the remote repository.
3. Ensure CI/CD pipelines are triggered automatically.