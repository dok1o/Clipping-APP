"""SQLAlchemy models (single place for ORM entities; CONTRACTS §2)."""
from app.models.clip import Clip, ClipStatus
from app.models.clip_candidate import ClipCandidate
from app.models.job import Job, JobRefType, JobStatus, JobType
from app.models.metric import Metric
from app.models.platform_account import PlatformAccount
from app.models.publication import Publication, PublicationStatus
from app.models.rendered_asset import RenderedAsset, RenderedAssetStatus
from app.models.rewards import (
    CampaignBriefVersion,
    CampaignTermsStatus,
    CampaignSourceAsset,
    CampaignTermsVersion,
    PayoutModel,
    RewardCampaign,
    RewardCampaignStatus,
    SourceAssetKind,
)
from app.models.training_run import TrainingRun
from app.models.transcript import TranscriptSegment
from app.models.video import Video, VideoStatus

__all__ = [
    "Video",
    "VideoStatus",
    "Clip",
    "ClipStatus",
    "Job",
    "JobStatus",
    "JobType",
    "JobRefType",
    "RenderedAsset",
    "RenderedAssetStatus",
    "PlatformAccount",
    "Publication",
    "PublicationStatus",
    "TranscriptSegment",
    "ClipCandidate",
    "Metric",
    "TrainingRun",
    "RewardCampaign",
    "RewardCampaignStatus",
    "CampaignTermsVersion",
    "CampaignBriefVersion",
    "CampaignTermsStatus",
    "CampaignSourceAsset",
    "SourceAssetKind",
    "PayoutModel",
]
