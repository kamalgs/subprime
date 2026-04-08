"""Investor persona definitions — the independent variable of the experiment."""

from pydantic import BaseModel, Field
from typing import Literal


class InvestorPersona(BaseModel):
    """A synthetic investor profile used as input to the advisor agent."""

    id: str = Field(description="Unique persona identifier, e.g. 'P01'")
    name: str = Field(description="Fictional name for readability")
    age: int = Field(ge=18, le=80)
    risk_appetite: Literal["conservative", "moderate", "aggressive"] = Field(
        description="Self-reported risk tolerance"
    )
    investment_horizon_years: int = Field(ge=1, le=40)
    investible_surplus_monthly_inr: float = Field(
        ge=0, description="Monthly investible surplus in INR"
    )
    existing_corpus_inr: float = Field(ge=0, description="Existing investment corpus in INR")
    liabilities_inr: float = Field(ge=0, description="Outstanding liabilities in INR")
    financial_goals: list[str] = Field(
        description="List of financial goals, e.g. 'retirement corpus of 5Cr by age 60'"
    )
    life_stage: str = Field(
        description="Brief descriptor, e.g. 'young earner, single, no dependents'"
    )
    additional_context: str = Field(
        default="", description="Any other relevant context about the persona"
    )

    def to_prompt_str(self) -> str:
        """Format persona as a string suitable for inclusion in an LLM prompt."""
        goals = "\n".join(f"  - {g}" for g in self.financial_goals)
        return (
            f"Investor Profile: {self.name}\n"
            f"Age: {self.age} | Life Stage: {self.life_stage}\n"
            f"Risk Appetite: {self.risk_appetite}\n"
            f"Investment Horizon: {self.investment_horizon_years} years\n"
            f"Monthly Investible Surplus: ₹{self.investible_surplus_monthly_inr:,.0f}\n"
            f"Existing Corpus: ₹{self.existing_corpus_inr:,.0f}\n"
            f"Outstanding Liabilities: ₹{self.liabilities_inr:,.0f}\n"
            f"Financial Goals:\n{goals}"
        )
