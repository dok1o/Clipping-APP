from sqlalchemy import inspect

from app.infra.database import Base
from app.infra.models import Clip, Job, PlatformAccount, Publication, RenderedAsset, Video


def test_core_models_are_registered_in_metadata() -> None:
    assert {Video, Clip, Job, RenderedAsset, PlatformAccount, Publication}
    assert set(Base.metadata.tables) == {
        "videos",
        "clips",
        "jobs",
        "rendered_assets",
        "platform_accounts",
        "publications",
    }


def test_core_foreign_keys_exist() -> None:
    assert _foreign_key_targets(Clip.__table__.c.video_id) == {"videos.id"}
    assert _foreign_key_targets(RenderedAsset.__table__.c.clip_id) == {"clips.id"}
    assert _foreign_key_targets(Publication.__table__.c.clip_id) == {"clips.id"}
    assert _foreign_key_targets(Publication.__table__.c.account_id) == {"platform_accounts.id"}


def test_core_relationships_exist() -> None:
    assert inspect(Clip).relationships["video"].mapper.class_ is Video
    assert inspect(RenderedAsset).relationships["clip"].mapper.class_ is Clip
    assert inspect(Publication).relationships["clip"].mapper.class_ is Clip
    assert inspect(Publication).relationships["account"].mapper.class_ is PlatformAccount


def _foreign_key_targets(column) -> set[str]:
    return {fk.target_fullname for fk in column.foreign_keys}
