from app.db.session import Base, engine
from app.worker.runtime import Worker


def main() -> None:
    Base.metadata.create_all(bind=engine)
    Worker().run_forever()


if __name__ == "__main__":
    main()
