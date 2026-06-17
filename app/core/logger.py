import logging, sys, structlog

# 1️⃣  processors that run for *every* log entry
shared_processors = [
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.CallsiteParameterAdder(
        {
            structlog.processors.CallsiteParameter.FILENAME,
            structlog.processors.CallsiteParameter.MODULE,
            structlog.processors.CallsiteParameter.LINENO,
            structlog.processors.CallsiteParameter.FUNC_NAME,
        }
    ),
    structlog.processors.format_exc_info,
]

# 2️⃣  structlog: add wrap_for_formatter **as the last processor**
structlog.configure(
    processors=shared_processors + [
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,  # <-- keeps event_dict
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

# 3️⃣  Console handler that renders with colours
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(
    structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,               # run same chain
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=True)
        ],
    )
)

# 4️⃣  Root logger wiring
root = logging.getLogger()
root.setLevel(logging.DEBUG)
root.handlers.clear()
root.addHandler(console_handler)

# 5️⃣  Silence noisy libs (unchanged)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("geventwebsocket.handler").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING) 

# for lib in (
#     "openai", "httpcore", "httpx", "werkzeug",
#     "sqlalchemy.engine", "geventwebsocket.handler", "urllib3",
# ):
#     logging.getLogger(lib).setLevel(logging.WARNING)

logger = structlog.get_logger(__name__)