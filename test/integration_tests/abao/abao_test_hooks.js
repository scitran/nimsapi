var hooks = require('hooks');

// Variables for passing results as input to subsequent tests
var job_id = '';
var gear_name = 'test-case-gear';
var group_id = 'test_group';
var collection_id = '';
var delete_collection_id = '';
var session_id = '';
var delete_session_id = '';

// Tests we're skipping, fix these

// Fails only in travis
hooks.skip("GET /version -> 200");

// Should 400 to say invalid json
hooks.skip("GET /download -> 400");

// Should 422 for missing metadata field
hooks.skip("POST /upload/label -> 402");
hooks.skip("POST /upload/uid -> 402");
hooks.skip("POST /upload/uid-match -> 402");

// Should 404
hooks.skip("GET /jobs/{JobId} -> 404");

// Can only retry a failed job
hooks.skip("POST /jobs/{JobId}/retry -> 200");

// https://github.com/cybertk/abao/issues/160
hooks.skip("GET /users/self/avatar -> 307");
hooks.skip("GET /users/{UserId}/avatar -> 307");

// Tests that are skipped because we do them in postman or python

// Skipping because abao doesn't support file fields
hooks.skip("POST /download -> 200");
hooks.skip("GET /download -> 200");
hooks.skip("POST /upload/label -> 200");
hooks.skip("POST /upload/uid -> 200");
hooks.skip("POST /upload/uid-match -> 200");
hooks.skip("POST /upload/uid-match -> 404");
hooks.skip("POST /engine -> 200");

// Needs a project to be added, tested with postman workflow test
hooks.skip("POST /sessions -> 200");

hooks.beforeEach(function (test, done) {
    test.request.query.root = "true"
    test.request.headers.Authorization = "scitran-user XZpXI40Uk85eozjQkU1zHJ6yZHpix+j0mo1TMeGZ4dPzIqVPVGPmyfeK";
    done();
});

hooks.after("GET /jobs -> 200", function(test, done) {
    job_id = test.response.body[0]._id;
    done();
});

hooks.before("GET /jobs/{JobId} -> 200", function(test, done) {
    test.request.params = {
        JobId: job_id
    };
    done();
});

hooks.before("GET /jobs/{JobId}/config.json -> 200", function(test, done) {
    test.request.params = {
        JobId: job_id
    };
    done();
});


hooks.before("PUT /jobs/{JobId} -> 200", function(test, done) {
    test.request.params = {
        JobId: job_id
    };
    done();
});

hooks.before("POST /jobs/{JobId}/retry -> 200", function(test, done) {
    test.request.params = {
        JobId: job_id
    };
    done();
});

hooks.before("GET /jobs/{JobId} -> 404", function(test, done) {
    test.request.params = {
        JobId: '57ace4479e512c61bc6e006f' // fake ID, 404
    };
    done();
});

hooks.before("GET /download -> 404", function(test, done) {
    test.request.query = {
        ticket: '1234'
    };
    done();
});

hooks.before("POST /users -> 400", function(test, done) {
    test.request.body = {api_key:{key:"test"}};
    done();
});

hooks.before("GET /users/{UserId} -> 200", function(test, done) {
    test.request.params = {
        UserId: "jane.doe@gmail.com"
    };
    done();
});

hooks.before("PUT /users/{UserId} -> 200", function(test, done) {
    test.request.params = {
        UserId: "jane.doe@gmail.com"
    };
    done();
});

hooks.before("PUT /users/{UserId} -> 400", function(test, done) {
    test.request.params = {
        UserId: "jane.doe@gmail.com"
    };
    test.request.body = {"not_a_valid_property":"foo"};
    done();
});

hooks.before("DELETE /users/{UserId} -> 200", function(test, done) {
    test.request.params = {
        UserId: "jane.doe@gmail.com"
    };
    done();
});

hooks.before("GET /gears/{GearName} -> 200", function(test, done) {
    test.request.params = {
        GearName: gear_name
    };
    done();
});

hooks.before("POST /gears/{GearName} -> 200", function(test, done) {
    test.request.params = {
        GearName: gear_name
    };
    done();
});

hooks.before("GET /gears/{GearName} -> 200", function(test, done) {
    test.request.params = {
        GearName: gear_name
    };
    done();
});

hooks.before("GET /groups -> 200", function(test, done) {
    // POST happens after GET, so hardcode a group_id
    // group_id = test.response.body[0]._id;
    done();
});

hooks.before("PUT /groups/{GroupId} -> 400", function(test, done) {
    test.request.params = {
        GroupId: group_id
    };
    test.request.body = {"not_a_real_property":"foo"};
    done();
});

hooks.before("POST /groups -> 400", function(test, done) {
    test.request.body = {"not_a_real_property":"foo"};
    done();
});


hooks.before("GET /groups/{GroupId} -> 200", function(test, done) {
    test.request.params = {
        GroupId: group_id
    };
    done();
});



hooks.before("DELETE /groups/{GroupId} -> 200", function(test, done) {
    test.request.params = {
        GroupId: group_id
    };
    done();
});

hooks.after("GET /collections -> 200", function(test, done) {
    collection_id = test.response.body[0]._id;
    delete_collection_id = test.response.body[1]._id;
    done();
});

hooks.before("GET /collections/{CollectionId} -> 200", function(test, done) {
    test.request.params.CollectionId = collection_id;
    done();
});

hooks.before("GET /collections/{CollectionId}/sessions -> 200", function(test, done) {
    test.request.params.CollectionId = collection_id;
    done();
});

hooks.before("GET /collections/{CollectionId}/acquisitions -> 200", function(test, done) {
    test.request.params.CollectionId = collection_id;
    done();
});

hooks.before("POST /collections -> 400", function(test, done) {
    test.request.params.CollectionId = collection_id;
    test.request.body.foo = "not an allowed property";
    done();
});

hooks.before("PUT /collections/{CollectionId} -> 400", function(test, done) {
    test.request.params.CollectionId = collection_id;
    test.request.body.foo = "not an allowed property";
    done();
});

hooks.before("DELETE /collections/{CollectionId} -> 200", function(test, done) {
    test.request.params.CollectionId = delete_collection_id;
    done();
});

hooks.after("GET /sessions -> 200", function(test, done) {
    session_id = test.response.body[0]._id;
    delete_session_id = test.response.body[1]._id;
    done();
});

hooks.before("GET /sessions/{SessionId} -> 200", function(test, done) {
    test.request.params.SessionId = session_id;
    done();
});

hooks.before("POST /sessions -> 400", function(test, done) {
    test.request.body.foo = "not an allowed property";
    done();
});
