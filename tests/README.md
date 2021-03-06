# Integration Tests

The Go packages have their own tests, but this contains higher-level
integration tests run with [pytest](https://docs.pytest.org/en/latest/).  The
tests need access to the Docker Engine API to start up test services.

These tests run the agent and associated packaging in a more fully functional
environment, along with a fake backend that simulates the SignalFx ingest and
API servers.  

To run all of them in parallel, simply invoke `pytest tests -n auto` from the
root of the repo in the dev image (see warning below for kubernetes
limitations). You can run individual test files by replacing `tests` with the 
relative path to the test Python module. You can also use the `-k` and `-m` 
flags to pick tests by name or tags, respectively.

A key goal in writing these tests is that they be both fully parallelizable to
minimize run time, and very robust with minimal transient failures due to
timing issues or race conditions that are so prevalent with integration
testing.  Please keep these goals in mind when adding integration tests.

These tests will be run automatically by CircleCI upon each commit.

**Note:** By default, the kubernetes tests will use the locally built
signalfx-agent docker image (i.e. the "final" image built by `make image`).  
Alternatively, you can also specify the name of the image and tag of the agent
with the `--k8s-agent-name=IMAGE_NAME` and `--k8s-agent-tag=IMAGE_TAG` pytest
options, respectively (if the image does not exist in the local registry, the 
test will try to pull the image from the remote registry).

For example, the following commands will build the "final" agent image, the dev
image, and run the kubernetes tests with the default options within the dev
image:
```
% cd <root_of_cloned_repo>
% make image
% make dev-image
% make run-dev-image
%% pytest -m k8s tests
```

Run `pytest --help` from the root of the repo in the dev image and see the 
"custom options" section of the output for more details and other available 
options.

**Warning:** Due to known limitations of the xdist pytest plugin (e.g. the 
`-n auto` option) for parametrized tests and fixtures, parallelization of
concurrent kubernetes tests is not yet fully supported.  Since the tests are 
designed to reuse the minikube and other fixtures for the test environment, 
invoking the xdist plugin may cause race conditions or duplicate executions of 
fixtures when running concurrent kubernetes tests.

