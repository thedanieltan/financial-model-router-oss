"""Provider-neutral routing core.

WP1 establishes this import boundary. Implementations arrive in subsequent work
packages; compatibility routing remains at its existing module paths until then.
"""

from fmr.core.families import FAMILIES, ModelFamilyDefinition, classify_job
from fmr.core.jobs import JobConstraints, ModelJob
from fmr.core.policies import DEFAULT_POLICY, LOCAL_ONLY_POLICY, RoutingPolicy, routing_policy
from fmr.core.routing import route_job
from fmr.core.scoping import (
    create_model_intent,
    create_scope_assessment,
    create_scope_candidate,
    create_scope_confirmation,
    validate_model_intent,
    validate_scope_assessment,
    validate_scope_candidate,
    validate_scope_confirmation,
)

__all__ = ["DEFAULT_POLICY", "FAMILIES", "JobConstraints", "LOCAL_ONLY_POLICY", "ModelFamilyDefinition", "ModelJob", "RoutingPolicy", "classify_job", "create_model_intent", "create_scope_assessment", "create_scope_candidate", "create_scope_confirmation", "route_job", "routing_policy", "validate_model_intent", "validate_scope_assessment", "validate_scope_candidate", "validate_scope_confirmation"]
