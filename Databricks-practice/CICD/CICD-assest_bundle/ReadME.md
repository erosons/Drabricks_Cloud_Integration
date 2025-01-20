# https://docs.databricks.com/en/dev-tools/bundles/index.html
https://docs.databricks.com/en/dev-tools/cli/install.html
https://docs.databricks.com/en/dev-tools/bundles/resource-examples.html

Databricks Asset Bundles (DABs) is a declarative configuratons format that allows you capture the three componenets below, this to facilitate the adoption of software engineering best practices, including source control, code review, testing, and continuous integration and delivery (CI/CD), 
Three key Components DABS
 - # Code/Sources
    - DB- Notebooks
    - Libraries(Python,Wheels)
    - SQL Files
    - JARS
 - # Resource Configuration
    - Databricks WorkFlow
    - Delta Live Table
    - Model Servicing Endpoint
    - Lakehouse Monitoring
 - # Environment Separation
    - Workspaces(Dev ,QA ,Production)
    - Catalog/Schema(bronze,Silver,Gold )
    - Execution Identity
       - (user / Service Principal)

**Bundles provide a way to include metadata alongside your project’s source files. When you deploy a project using bundles, this metadata is used to provision infrastructure and other resources.** 

Your project’s collection of source files/resource files and metadata is then deployed as a single bundle to your target environment. A bundle includes the following parts:

    - Required cloud infrastructure and workspace configurations (Optional to be handled in Terraform) 

    - Source files, such as notebooks and Python files, that include the business logic

    - Definitions and settings for Databricks resources, such as Databricks jobs, Delta Live Tables pipelines, Model Serving endpoints, MLflow Experiments, and MLflow registered models

    - Unit tests and integration tests

    - Single source of Truth for code and resource configuragtion

    - Define and managed resources through YAML templates and files you create and maintain alongside source code, they map well to scenarios where IaC is an appropriate approach.

    - Specialize resources base on target environment (dev/Staging/prod)

    - Deployment isolation
    
    - Write code onces and deploy to multiples workspaces esily  ?

The following diagram provides a high-level view of a development and CI/CD pipeline with bundles:


## When should I use Databricks Asset Bundles?

Databricks Assets Bundles are an infrastructure-as-code (IaC) approach to managing your Databricks projects. Use them when you want to manage complex projects where multiple contributors and automation are essential, and continuous integration and deployment (CI/CD) are a requirement. 

Since bundles are defined and managed through YAML templates and files you create and maintain alongside source code, they map well to scenarios where IaC is an appropriate approach.


## How do Databricks Asset Bundles work?

- The Databricks CLI can then be used to validate, deploy, and run bundles using these bundle YAML files. You can run bundle projects from IDEs, terminals, or within Databricks directly. This article uses the Databricks CLI.

Bundles can be created manually or based on a template. The Databricks CLI provides default templates for simple use cases, but for more specific or complex jobs, you can create custom bundle templates.

# Initializing DAB templates
   >> databricks bundle init default-python
   >> databricks bundle init default-sql
   >> databricks bundle init dbt-sql
   >> databricks bundle init mlops-stacks

# Deployment process
   # deploys the pipeline
    >> databrcks bundle deploy -e "dev" 
    >> databricks bundle deploy --target prod --profile Production
   # Runs the job for the first time
    >> databricks bundle run pipline -refresh-all -e  "dev"
    >> 




