## 1. File Utilities (dbutils.fs)

    >>> ls(path): Lists the files and directories in the specified path.
    >>> mv(src_path, dst_path): Moves a file or directory from one location to another.
    >>> cp(src_path, dst_path, recurse=False): Copies a file or directory to a new location, with an option to recurse through directories.
    >>> rm(path, recurse=False): Deletes a file or directory, with an option to recurse through directories.
    >>> mkdirs(path): Creates a directory and necessary parent directories.
    >>> mount(source, mount_point, encryption_type=None, owner=None, extra_configs=None): Mounts a storage object to DBFS.
    >>> unmount(mount_point): Unmounts the specified mount point.
    >>> refreshMounts(): Refreshes mounts to ensure updated access.
    >>> help(): Provides help on the file utilities.

## 2. Database Utilities (dbutils.notebook)

    >>> run(path, timeout_seconds, arguments=None): Runs another notebook in the workspace, passing in optional arguments and a timeout.
    >>> exit(value): Exits the notebook with the specified return value.
    >>> help(): Provides help on the notebook utilities.

## 3. Secret Utilities (dbutils.secrets)

    >> get(scope, key): Retrieves a secret value from a secret scope.
    >> listScopes(): Lists all secret scopes.
    >>> list(scope): Lists all secrets in a given scope.
    >>> help(): Provides help on the secret utilities.

## 4. Widgets Utilities (dbutils.widgets)

    >> text(name, defaultValue="", label=""): Creates a text input widget.
    >>> dropdown(name, defaultValue, choices, label=""): Creates a dropdown menu.
    >> combobox(name, defaultValue, choices, label=""): Creates a combobox that allows both dropdown and free-form text.
    >> multiselect(name, defaultValue, choices, label=""): Creates a multi-select box.
    >>> remove(name): Removes a widget.
    >>> removeAll(): Removes all widgets.
    >> get(name): Gets the current value of a widget.
    >>> help(): Provides help on the widgets utilities.

## 5. Preview Utilities (dbutils.data)

    >> preview(path, offset=0, length=1024): Previews data in a file at the specified path.
    >>> help(): Provides help on the preview utilities.

## 6. Library Utilities (dbutils.library)

    >> installPyPI(package, version=None, repo=None): Installs a Python package from PyPI.
    >> installMaven(coordinates, repo=None, exclusions=None): Installs a Maven package.
    >> installCran(package, repo=None, version=None): Installs a CRAN package.
    >>> uninstall(package): Uninstalls a package.
    >>> list(): Lists all installed libraries.
    >>> restartPython(): Restarts the Python interpreter on the current cluster.
    >>> help(): Provides help on the library utilities.

These utilities integrate deeply within the Databricks environment, making it easier to perform a range of tasks directly from the notebook interface. You can access detailed documentation and additional options by calling the help() function on any of these utilities within a Databricks notebook to explore more functionalities.