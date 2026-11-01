# DRISHTI access policy (Open Policy Agent, Rego v1).
# Mirrors drishti/guard/policy.py::_decide_local. Run with:
#   opa run --server --addr :8181 policies/
# and set DRISHTI_OPA_URL=http://localhost:8181
package drishti.access

import rego.v1

default decision := {"allow": false, "reason": "default deny"}

oversight_only if {
	some r in input.user.roles
	r in {"auditor", "admin"}
	not operational_role
}

operational_role if {
	some r in input.user.roles
	r in {"io", "supervisor", "analyst", "viewer", "operator", "collector"}
}

in_jurisdiction if "*" in input.user.districts

# place-less identifiers (phones, accounts) are governed by case membership alone.
# Two rules: `not x` covers a missing key, but JSON null is a value, so it needs `== null`.
in_jurisdiction if not input.object.district

in_jurisdiction if input.object.district == null

in_jurisdiction if input.object.district in input.user.districts

in_jurisdiction if input.case.scope_contains_object

# purpose limitation by record class; an object admitted to the case scope stays readable
purpose_allows if input.object.record_class in input.case.record_classes

purpose_allows if input.case.scope_contains_object

decision := {"allow": true, "reason": "public"} if {
	input.object.sensitivity == 0
} else := {"allow": false, "reason": "separation of duties: oversight and admin roles cannot read operational data"} if {
	oversight_only
} else := {"allow": false, "reason": "clearance below object sensitivity"} if {
	input.user.clearance < input.object.sensitivity
} else := {"allow": false, "reason": "purpose required: no active case"} if {
	input.case == null
} else := {"allow": false, "reason": "case is closed"} if {
	input.case.status != "open"
} else := {"allow": false, "reason": "not a member of the active case"} if {
	not input.user.id in input.case.members
} else := {"allow": false, "reason": "record class outside the case purpose"} if {
	not purpose_allows
} else := {"allow": false, "reason": "outside jurisdiction and not in case scope"} if {
	not in_jurisdiction
} else := {"allow": true, "reason": "case member within clearance and jurisdiction"}

allow := decision.allow
