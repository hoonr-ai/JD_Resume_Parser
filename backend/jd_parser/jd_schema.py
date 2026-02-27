from pydantic import BaseModel, Field, model_validator
from typing import List, Dict


class Skill(BaseModel):
    skill_id: str
    canonical_name: str
    minimum_years: float
    required_proficiency_level: int = Field(ge=1, le=5)
    mandatory: bool
    weight: float = Field(ge=0, le=1)


class JDSkillRequirements(BaseModel):
    jd_id: str
    required_skills: List[Skill]
    optional_skills: List[Skill] = []
    category_distribution: Dict[str, float] = {}

    @model_validator(mode="after")
    def validate_weight_distribution(self):
        """Ensure weights sum to 1"""

        def check(skills, label):
            if not skills:
                return

            total = sum(s.weight for s in skills)

            if abs(total - 1.0) > 0.01:
                raise ValueError(
                    f"{label} weights must sum to 1, got {total}"
                )

        check(self.required_skills, "required_skills")
        check(self.optional_skills, "optional_skills")

        return self


class TOON(BaseModel):
    jd_skill_requirements: JDSkillRequirements


class JDResponse(BaseModel):
    TOON: TOON