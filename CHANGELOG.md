# Changelog

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
