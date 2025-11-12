from pyspark.dbutils import DBUtils
dbutils = DBUtils(spark)

ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
CURRENT_NOTEBOOK_PATH = ctx.notebookPath().get()   # e.g. /Repos/user/repo/path/app.py
WORKSPACE_ROOT = "/"

# optional: current repo root (when running in Repos)
try:
    REPO_ROOT = CURRENT_NOTEBOOK_PATH.rsplit("/", 2)[0]
except Exception:
    REPO_ROOT = None

print(REPO_ROOT, CURRENT_NOTEBOOK_PATH)