"""代理人介面。UtilityAgent 為現行實作；LLMAgent 為第二階段，需實作相同的 wishlist()。"""
from __future__ import annotations

from typing import Protocol

import numpy as np

from .population import Student
from .utility import Betas, ElectivePool


class Agent(Protocol):
    student: Student

    def wishlist(self) -> list[tuple[str, float]]:
        """回傳依偏好排序的 (course_id, utility)；機制會依序嘗試。"""
        ...


class UtilityAgent:
    def __init__(self, student: Student, pool: ElectivePool, betas: Betas,
                 rng: np.random.Generator, max_list: int = 15):
        self.student = student
        self.pool = pool
        self.betas = betas
        self.rng = rng
        self.max_list = max_list

    def utilities(self) -> np.ndarray:
        s, b = self.student, self.betas
        v = self.pool.systematic(s, b)
        return v + b.noise * self.rng.gumbel(size=len(v))

    def wishlist(self) -> list[tuple[str, float]]:
        u = self.utilities()
        order = np.argsort(-u)
        out = []
        for i in order:
            if u[i] <= self.betas.outside or len(out) >= self.max_list:
                break
            out.append((self.pool.feats[i].id, float(u[i])))
        return out


class LLMAgent:  # 第二階段
    def __init__(self, *_, **__):
        raise NotImplementedError("LLM 代理人留待第二階段，介面同 UtilityAgent.wishlist()")
