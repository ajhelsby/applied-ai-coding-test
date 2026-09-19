# Changelog

## [0.0.8](https://github.com/ajhelsby/applied-ai-coding-test/compare/v0.0.7...v0.0.8) (2026-09-19)


### Bug Fixes

* **#96:** Update documentation to clarify Docker Compose setup and API connection details ([#97](https://github.com/ajhelsby/applied-ai-coding-test/issues/97)) ([2e0a3b3](https://github.com/ajhelsby/applied-ai-coding-test/commit/2e0a3b3be6c19c83355ce612400aa7c90a40fac5))


### Docs

* **#41:** Document design decisions and system architecture for work ([#94](https://github.com/ajhelsby/applied-ai-coding-test/issues/94)) ([a0c21f8](https://github.com/ajhelsby/applied-ai-coding-test/commit/a0c21f888bd6c90c4bf17277763041c92d0ec3a0))

## [0.0.7](https://github.com/ajhelsby/applied-ai-coding-test/compare/v0.0.6...v0.0.7) (2026-09-18)


### Features

* **#38:** Add race-condition test ([#88](https://github.com/ajhelsby/applied-ai-coding-test/issues/88)) ([eda4633](https://github.com/ajhelsby/applied-ai-coding-test/commit/eda4633d1720b93a355628bc0765a6de963d2cef))
* **#39:** Test idempotency by delivering duplicate Redis task messages and verifying consistent processing and ([#89](https://github.com/ajhelsby/applied-ai-coding-test/issues/89)) ([81c1e08](https://github.com/ajhelsby/applied-ai-coding-test/commit/81c1e08654549a3cc72663afaee2574329304bc0))


### Bug Fixes

* **#92:** Fix task retry logic, update polling condition, add default config in test nodes, and improve test a ([#93](https://github.com/ajhelsby/applied-ai-coding-test/issues/93)) ([50adde5](https://github.com/ajhelsby/applied-ai-coding-test/commit/50adde53ec2c185ad833d22d227c2cf02f5d18fa))


### Tests

* **#35:** Update testing instructions with detailed guidance on test structure, layers, and best practices ([#84](https://github.com/ajhelsby/applied-ai-coding-test/issues/84)) ([e40b4af](https://github.com/ajhelsby/applied-ai-coding-test/commit/e40b4af2c02fa3aea794fbbc1dcca6621ba63ca3))
* **#36:** Add improved integration tests ([#86](https://github.com/ajhelsby/applied-ai-coding-test/issues/86)) ([3e3dcc4](https://github.com/ajhelsby/applied-ai-coding-test/commit/3e3dcc4ce63deb4b30db2635db79e7b716364e96))
* **#37:** Add fan-out/fan-in integration test ([#87](https://github.com/ajhelsby/applied-ai-coding-test/issues/87)) ([554cff9](https://github.com/ajhelsby/applied-ai-coding-test/commit/554cff97a97648bf18eaba9f3a9fd5bc7a66c14c))
* **#40:** Add API integration tests ([#90](https://github.com/ajhelsby/applied-ai-coding-test/issues/90)) ([9c1ddd4](https://github.com/ajhelsby/applied-ai-coding-test/commit/9c1ddd4a71b1332c6eb6933b8482b267f09c7091))
* **#43:** Add test for docker ([#91](https://github.com/ajhelsby/applied-ai-coding-test/issues/91)) ([b5a7011](https://github.com/ajhelsby/applied-ai-coding-test/commit/b5a701175a0eb1a7a3cede387ae79c5a1fde130f))

## [0.0.6](https://github.com/ajhelsby/applied-ai-coding-test/compare/v0.0.5...v0.0.6) (2026-09-16)


### Features

* **#31:** Add persistent worker task-processing state with associate… ([#79](https://github.com/ajhelsby/applied-ai-coding-test/issues/79)) ([cf0ee67](https://github.com/ajhelsby/applied-ai-coding-test/commit/cf0ee676f20ca9b5b3d3d794cb6d1690720a503c))
* **#32:** Add durable task attempt and retry state management features ([#81](https://github.com/ajhelsby/applied-ai-coding-test/issues/81)) ([14b7382](https://github.com/ajhelsby/applied-ai-coding-test/commit/14b73823697f3a73fc6b0f4df014cee9ae492fb0))
* **#33:** Add logic to skip nodes on dependency failures ([#82](https://github.com/ajhelsby/applied-ai-coding-test/issues/82)) ([3949e8b](https://github.com/ajhelsby/applied-ai-coding-test/commit/3949e8b7583b6ae775a1adb1cb52cb4a901f2d79))
* **#34:** Generalize outbox message schema and add support for task messages ([#83](https://github.com/ajhelsby/applied-ai-coding-test/issues/83)) ([6b4629d](https://github.com/ajhelsby/applied-ai-coding-test/commit/6b4629d384212a6710e653d0b7436d270f4581e1))

## [0.0.5](https://github.com/ajhelsby/applied-ai-coding-test/compare/v0.0.4...v0.0.5) (2026-09-15)


### Features

* **#20:** Implement row-level locking for workflow execution retrieval to ensure concurrency safety ([#73](https://github.com/ajhelsby/applied-ai-coding-test/issues/73)) ([78d2aaa](https://github.com/ajhelsby/applied-ai-coding-test/commit/78d2aaae39675a38381054deb3016e24dd228443))
* **#21:** Add claim_pending_nodes method to repository and services for atomic node claiming ([#75](https://github.com/ajhelsby/applied-ai-coding-test/issues/75)) ([1999412](https://github.com/ajhelsby/applied-ai-coding-test/commit/199941257fa0e221291ceddb80ae5fe97fdb3942))
* **#22:** Allow node output data to be null and update related model… ([#76](https://github.com/ajhelsby/applied-ai-coding-test/issues/76)) ([7bd08ff](https://github.com/ajhelsby/applied-ai-coding-test/commit/7bd08ffee62c4baaa58bb500c6824fc5b47cf139))
* **#23:** Add template parser ([#77](https://github.com/ajhelsby/applied-ai-coding-test/issues/77)) ([f769579](https://github.com/ajhelsby/applied-ai-coding-test/commit/f769579537311a2b326984be884b205883a3f5c9))

## [0.0.4](https://github.com/ajhelsby/applied-ai-coding-test/compare/v0.0.3...v0.0.4) (2026-09-14)


### Features

* **#26:** Add handler registry with default and custom handler resolution logic ([#68](https://github.com/ajhelsby/applied-ai-coding-test/issues/68)) ([297317b](https://github.com/ajhelsby/applied-ai-coding-test/commit/297317b33368686b19aa1f0c46db60cc1e3a8531))
* **#27:** Add workflow trigger consumer for processing execution tri… ([#71](https://github.com/ajhelsby/applied-ai-coding-test/issues/71)) ([9bb8f6e](https://github.com/ajhelsby/applied-ai-coding-test/commit/9bb8f6e765a284bce3da558ffaf736fd2af50380))
* **#28:** Add configurable mock external service environment variables and deterministic response logic ([#72](https://github.com/ajhelsby/applied-ai-coding-test/issues/72)) ([18e8edf](https://github.com/ajhelsby/applied-ai-coding-test/commit/18e8edf8ce456bc08bd6ed54f8a92fc6c8fcc9e9))
* **#29:** Add mock LLM service node handler implementation with dete… ([#70](https://github.com/ajhelsby/applied-ai-coding-test/issues/70)) ([a8846f1](https://github.com/ajhelsby/applied-ai-coding-test/commit/a8846f1cf774364652ffd30b1f76c8b11fc22ccd))

## [0.0.3](https://github.com/ajhelsby/applied-ai-coding-test/compare/v0.0.2...v0.0.3) (2026-09-08)


### Features

* **#17:** Implement dependency-based node readiness evaluation and corresponding tests ([#64](https://github.com/ajhelsby/applied-ai-coding-test/issues/64)) ([a64f684](https://github.com/ajhelsby/applied-ai-coding-test/commit/a64f68456214b1230cca8c16b5ddebeef16913ca))
* **#19:** Task completion event handling ([#66](https://github.com/ajhelsby/applied-ai-coding-test/issues/66)) ([eab3add](https://github.com/ajhelsby/applied-ai-coding-test/commit/eab3add6d8de3d59dfd869f8e19692dc321d21ad))
* **#25:** Add detailed design documentation for worker message handling and recovery strategies ([#67](https://github.com/ajhelsby/applied-ai-coding-test/issues/67)) ([a88432c](https://github.com/ajhelsby/applied-ai-coding-test/commit/a88432ca5ee2a032b3de94d1f81e4f3171661098))

## [0.0.2](https://github.com/ajhelsby/applied-ai-coding-test/compare/v0.0.1...v0.0.2) (2026-09-08)


### Features

* **#10:** Refactor dependency rules to check for unknown, self, and duplicate dependencies ([#51](https://github.com/ajhelsby/applied-ai-coding-test/issues/51)) ([ae1ae29](https://github.com/ajhelsby/applied-ai-coding-test/commit/ae1ae29881bf796f5c8f09545a4672d9029370ad))
* **#11:** Cycle validation ([#52](https://github.com/ajhelsby/applied-ai-coding-test/issues/52)) ([bcbd787](https://github.com/ajhelsby/applied-ai-coding-test/commit/bcbd7876279efe55c85accd7c1dcc16c0afff815))
* **#13:** Implement workflow submission endpoint with validation, persistence, and error handling ([#54](https://github.com/ajhelsby/applied-ai-coding-test/issues/54)) ([85c1919](https://github.com/ajhelsby/applied-ai-coding-test/commit/85c1919dab89d74119b94388da5c0d9feebbe1d0))
* **#14:** workflow execution endpoint ([#55](https://github.com/ajhelsby/applied-ai-coding-test/issues/55)) ([b879744](https://github.com/ajhelsby/applied-ai-coding-test/commit/b879744af759659ad70f8a4d82fbaeea8b428107))
* **#15:** Add API endpoint to retrieve workflow execution status with node details ([#56](https://github.com/ajhelsby/applied-ai-coding-test/issues/56)) ([abaaac4](https://github.com/ajhelsby/applied-ai-coding-test/commit/abaaac4e318e00f7b261474146c66dcbbefdadb3))
* **#16:** Add API endpoint to retrieve final workflow execution resu… ([#61](https://github.com/ajhelsby/applied-ai-coding-test/issues/61)) ([6258b67](https://github.com/ajhelsby/applied-ai-coding-test/commit/6258b67aec8ddf22f585bcd8f06dfb44b615e7c4))
* **#18:** Add Redis-based node task dispatcher for claiming nodes and publishing tasks asynchronously ([#62](https://github.com/ajhelsby/applied-ai-coding-test/issues/62)) ([43f1b2b](https://github.com/ajhelsby/applied-ai-coding-test/commit/43f1b2b99fcb3260d4705c30483ff9e92cdad84d))
* **#1:** initialise repo ([#2](https://github.com/ajhelsby/applied-ai-coding-test/issues/2)) ([1aea6c5](https://github.com/ajhelsby/applied-ai-coding-test/commit/1aea6c56432423cb1e58e58d3f6a1840540cc3ad))
* **#3:** Add Docker containerisation ([#44](https://github.com/ajhelsby/applied-ai-coding-test/issues/44)) ([b64729a](https://github.com/ajhelsby/applied-ai-coding-test/commit/b64729a640d221aec90256099db05e4c692b5331))
* **#4:** Add environment variable configurations, Alembic setup, and… ([#45](https://github.com/ajhelsby/applied-ai-coding-test/issues/45)) ([e433bf3](https://github.com/ajhelsby/applied-ai-coding-test/commit/e433bf341bef2023a0d31c92e9948a061edd83c6))
* **#5:** Add Redis streams support and infrastructure initialization… ([#46](https://github.com/ajhelsby/applied-ai-coding-test/issues/46)) ([e05570d](https://github.com/ajhelsby/applied-ai-coding-test/commit/e05570da9717c0923dd26611aa6f46113b3e341c))
* **#6:** Update GitHub action to run API entry-point tests and revis… ([#47](https://github.com/ajhelsby/applied-ai-coding-test/issues/47)) ([4ca3e38](https://github.com/ajhelsby/applied-ai-coding-test/commit/4ca3e38eff2a05260dfe4b2cb95fc536a624cedf))
* **#7:** Add state machine transition validation and exceptions for workflow and node states ([#48](https://github.com/ajhelsby/applied-ai-coding-test/issues/48)) ([c71ee21](https://github.com/ajhelsby/applied-ai-coding-test/commit/c71ee214944dbd38a0eac8b70f341716317f7fe6))
* **#8:** Add database schema migrations and define domain repository… ([#49](https://github.com/ajhelsby/applied-ai-coding-test/issues/49)) ([846d42b](https://github.com/ajhelsby/applied-ai-coding-test/commit/846d42b4f53e0037f0cc06a2699387925a78a6ff))
* **#9:** DAG Validation layer and initial endpoint ([#50](https://github.com/ajhelsby/applied-ai-coding-test/issues/50)) ([76282ed](https://github.com/ajhelsby/applied-ai-coding-test/commit/76282ede23b55234312344ec5191f68b74676321))


### Bug Fixes

* **#18:** fix linting ([#63](https://github.com/ajhelsby/applied-ai-coding-test/issues/63)) ([7892077](https://github.com/ajhelsby/applied-ai-coding-test/commit/78920778fc3ec3d6f5045466f8944fa497e23886))
* **#57:** Update release-please workflow to use default GitHub token for authentication ([#58](https://github.com/ajhelsby/applied-ai-coding-test/issues/58)) ([ab42aeb](https://github.com/ajhelsby/applied-ai-coding-test/commit/ab42aebbf45fb9c19cfe27786f4f4fb9312ef9a9))
* **#57:** Update release-please workflow to use default GitHub token for authentication ([#59](https://github.com/ajhelsby/applied-ai-coding-test/issues/59)) ([a3a696f](https://github.com/ajhelsby/applied-ai-coding-test/commit/a3a696f090a9076b86a20641adf08b597010604d))


### Refactoring

* **#12:** Implement internal DAG graph representation with node dependencies and traversal methods ([#53](https://github.com/ajhelsby/applied-ai-coding-test/issues/53)) ([86aff57](https://github.com/ajhelsby/applied-ai-coding-test/commit/86aff57c646a327c44236e7984de8efac42cf682))
