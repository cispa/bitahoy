# Addon software development kit
This repo is not only intended to ease development of new addons, but as of now is a dependency for a lot of our modules.
Besides emulators to test addons there are a lot of helper funcitons for network protocols.


## Installation
- install python bindings

```
python setup.py install
```

## Usage

- look at the examples


## Using commit hooks
To improve code quality we added the [`pre-commit`](https://pre-commit.com/) package to requirements.txt.   
Simply run `pre-commit install` inside the repo.   
Then before committing it runs:   
1. [black](https://github.com/psf/black): automatically beautifies code:   
	You need to add the changes in order to commit.
	If `test.py` was modified you have to `git add test.py` before committing again to accept the changes.

2. [flake8](https://github.com/PyCQA/flake8/tree/3.9.2): lints the code and shows you unused variables or imports.   
	For violations starting with B you can look then up [here](https://pypi.org/project/flake8-bugbear/) as they are part of bugbear. The rest (E and W) can be found [here](https://www.flake8rules.com/).   
	If you believe that the way you are doing things is correct and pylint is too strict you can do the following:   

	`example = lambda: 'example'` violates *E731*. If you really need this lambda add:   
	`example = lambda: 'example'  # noqa: E731` the comment, so the error is ignored by the linter.
	
3. [bandit](https://bandit.readthedocs.io/en/latest/plugins/index.html#complete-test-plugin-listing): finds potential security vulnerabilities   
	After evaluating if highlighted problems are security relevant, you can fix the issue or comment the affected line out with `# nosec` to silence the warning.   
	This seems quite sensitive and is definitely an experimental addition to ci.

4. [isort](https://pycqa.github.io/isort/): reorders your imports

5. [mypy](https://mypy.readthedocs.io/en/stable/index.html): does variable type checking. If you need to ignore something use `# type: ignore`

6. [pytest](https://github.com/pytest-dev/pytest): runs our tests.   
	Caveats: Tests are run on the state of the repository that would be committed. That means if you modified a test that is not included in the commit it won't fail. You can directly run `pytest` to see if that is the case.

### Skipping hooks
If you need to skip a hook, e.g. because you wrote tests showing a bug and need to skip the pytest hook (because you want somebody else to fix the problem) you can run `SKIP=pytest git commit` to disable pytests for that commit. Please refrain from adding `SKIP` permanently to your env, since it decreases our CI performance.
