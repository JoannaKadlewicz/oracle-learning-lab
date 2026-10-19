"""Oracle Learning Lab: a study app for the Oracle SQL exams 1Z0-071 and 1Z0-171.

Package layout (dependencies point downwards only):

    cli, bootstrap      entry points and the composition root that wires everything together
    web                 HTTP adapter: routing, middleware, controllers, static files, report page
    services            use cases (study, mock exams, SQL lab, exercises), free of HTTP details
    study, grading      domain logic over the saved progress and the study content
    database, analysis  Oracle access, SQL execution and explanations of Oracle errors
    sqltext, content    pure SQL text helpers and the study material itself
    config, credentials settings from the environment, passwords from secret files
"""

__version__ = "2.0.0"
