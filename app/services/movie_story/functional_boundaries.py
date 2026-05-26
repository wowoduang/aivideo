# -*- coding: utf-8 -*-
from __future__ import annotations

"""
movie_story.functional_boundaries

这里提供“可被后续重构脚本/业务代码引用”的功能边界判断函数。

它和 functional_contracts.py 的关系：
- functional_contracts.py 保存静态契约数据；
- functional_boundaries.py 提供围绕这些契约的可复用函数。

为什么单独拆这个模块：
1. 后续拆大文件时，Claude Code/ChatGPT 需要一个稳定 API 判断模块能不能被新代码引用；
2. 旧 native/legacy 模块不能再靠口头约束防回流，应该有函数级 guard；
3. 长视频拆短视频相关模块虽然还在审查，但不能因为名字含 native/legacy 被误删。

本模块不 import 旧 native/legacy 实现，不执行运行时调度，只做轻量元数据判断。
"""

from dataclasses import dataclass
from pathlib import Path

from app.services.movie_story.functional_contracts import (
    ContractStatus,
    FlowName,
    FunctionalContract,
    active_reference_modules,
    iter_contracts,
    retired_candidate_modules,
)


@dataclass(frozen=True)
class ModuleBoundary:
    """一个模块在当前 movie_story 架构里的引用边界。

    字段说明：
    - module: Python dotted module path。
    - flow: 所属流程；未知模块为 None。
    - status: 契约状态；未知模块为 None。
    - can_reference_from_new_code: 新代码是否允许主动引用。
    - must_not_use_as_fallback: 是否禁止作为 fallback / 兼容入口接回主流程。
    - reason: 人类可读解释，供审计报告和错误信息使用。
    """

    module: str
    flow: FlowName | None
    status: ContractStatus | None
    can_reference_from_new_code: bool
    must_not_use_as_fallback: bool
    reason: str


def contract_for_module(module: str) -> FunctionalContract | None:
    """按模块路径查找功能契约。

    生产者：
        functional_contracts.CONTRACTS。

    消费者：
        后续重构脚本、架构 guard、测试和人工审计报告。

    设计原因：
        后续拆代码时不要到处手写字符串判断 retired/native/legacy，
        应该统一从契约表查。
    """

    normalized = module.strip()
    for contract in iter_contracts():
        if contract.module == normalized:
            return contract
    return None


def module_to_source_path(module: str) -> Path:
    """把 dotted module path 转成相对源码路径。

    示例：
        app.services.movie_story.two_round_narration
        -> app/services/movie_story/two_round_narration.py

    这个函数只做确定性路径转换，不检查文件是否存在。
    """

    return Path(*module.split(".")).with_suffix(".py")


def source_path_to_module(path: str | Path) -> str:
    """把源码路径转成 dotted module path。

    该函数用于审计工具把扫描到的文件路径映射回契约模块名。
    它只接受 .py 文件路径；其它后缀表示调用方传入了错误对象，应直接报错。
    """

    source_path = Path(path)
    if source_path.suffix != ".py":
        raise ValueError(f"source_path_must_be_python_file:{source_path}")
    return ".".join(source_path.with_suffix("").parts)


def classify_module_boundary(module: str) -> ModuleBoundary:
    """判断一个模块在当前架构里是否可被新代码引用。

    规则：
    - active_mainflow / active_support：允许新代码主动引用；
    - migration_value_review：允许审计/迁移代码引用，但不等于已经是稳定主流程；
    - retired_candidate：禁止新代码引用，尤其禁止作为 fallback 接回 movie_story；
    - 未登记模块：不直接禁止，但返回 unknown，要求调用方自行审查。
    """

    normalized = module.strip()
    contract = contract_for_module(normalized)

    if contract is None:
        return ModuleBoundary(
            module=normalized,
            flow=None,
            status=None,
            can_reference_from_new_code=False,
            must_not_use_as_fallback=True,
            reason=(
                "模块未登记在 movie_story 功能契约中；"
                "若要作为新代码依赖，必须先补契约说明生产者、消费者和维护边界。"
            ),
        )

    if contract.status == "retired_candidate":
        return ModuleBoundary(
            module=normalized,
            flow=contract.flow,
            status=contract.status,
            can_reference_from_new_code=False,
            must_not_use_as_fallback=True,
            reason=contract.notes,
        )

    return ModuleBoundary(
        module=normalized,
        flow=contract.flow,
        status=contract.status,
        can_reference_from_new_code=True,
        must_not_use_as_fallback=False,
        reason=contract.notes,
    )


def assert_new_code_may_reference(module: str, *, reason: str) -> None:
    """阻止后续补丁把待退休模块重新接回新代码。

    参数：
        module: 准备被新代码 import / 调用的模块。
        reason: 调用方给出的引用理由。必须显式填写，避免无说明地接入依赖。

    抛错：
        ValueError:
        - 模块是 retired_candidate；
        - 模块未登记；
        - 调用方没有提供引用理由。
    """

    if not reason.strip():
        raise ValueError("reference_reason_required")

    boundary = classify_module_boundary(module)
    if not boundary.can_reference_from_new_code:
        raise ValueError(
            "movie_story_module_reference_not_allowed:"
            f"{module}:{boundary.reason}"
        )


def mainflow_modules() -> tuple[str, ...]:
    """返回当前正式主流程模块。

    当前只应包含基础双轮链和第一轮前视觉增强链。
    长视频拆短视频目前仍拆在多个支撑模块中，未在这里声明为单一 orchestration 模块。
    """

    return tuple(
        contract.module
        for contract in iter_contracts()
        if contract.status == "active_mainflow"
    )


def support_modules() -> tuple[str, ...]:
    """返回当前正式支撑模块。

    这些模块可以被新代码引用，但不应被误解成独立主流程入口。
    """

    return tuple(
        contract.module
        for contract in iter_contracts()
        if contract.status == "active_support"
    )


def migration_review_modules() -> tuple[str, ...]:
    """返回需要继续审查/拆分的迁移价值模块。

    这些模块通常含确定性能力，例如 timeline、composition、highlight selection。
    它们不是 retired_candidate，不能因为历史命名直接删除。
    """

    return tuple(
        contract.module
        for contract in iter_contracts()
        if contract.status == "migration_value_review"
    )


def modules_blocked_for_new_runtime() -> tuple[str, ...]:
    """返回禁止新 runtime 主动引用的待退休模块。

    这通常用于审计工具或测试，防止旧 movie_story native/legacy 主流程回流。
    """

    return retired_candidate_modules()


def assert_contract_table_is_consistent() -> None:
    """检查功能契约表内部没有自相矛盾。

    当前保护点：
    - active_reference_modules 与 retired_candidate_modules 不得有交集；
    - 每个模块只能登记一次；
    - 每条契约都必须写清责任和维护说明。
    """

    modules = [contract.module for contract in iter_contracts()]
    duplicated = sorted({module for module in modules if modules.count(module) > 1})
    if duplicated:
        raise ValueError("duplicated_functional_contract_modules:" + ",".join(duplicated))

    active = set(active_reference_modules())
    retired = set(retired_candidate_modules())
    overlap = sorted(active & retired)
    if overlap:
        raise ValueError("active_retired_contract_overlap:" + ",".join(overlap))

    for contract in iter_contracts():
        if not contract.responsibility.strip() or not contract.notes.strip():
            raise ValueError(f"incomplete_functional_contract:{contract.module}")
