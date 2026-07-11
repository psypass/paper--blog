from paper_blog_agent.prompts.blog_modes.learning import GUIDANCE as LEARNING_GUIDANCE
from paper_blog_agent.prompts.blog_modes.popular import GUIDANCE as POPULAR_GUIDANCE
from paper_blog_agent.prompts.blog_modes.technical import GUIDANCE as TECHNICAL_GUIDANCE


BLOG_MODE_GUIDANCE = {
    "popular": POPULAR_GUIDANCE,
    "learning": LEARNING_GUIDANCE,
    "technical": TECHNICAL_GUIDANCE,
}

__all__ = ["BLOG_MODE_GUIDANCE"]
