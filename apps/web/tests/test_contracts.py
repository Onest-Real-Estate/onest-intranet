from django import forms

from apps.web.contracts import list_response, validation_errors


class ExampleForm(forms.Form):
    name = forms.CharField()

    def clean(self):
        super().clean()
        raise forms.ValidationError("The record changed while you were editing.")


def test_validation_errors_preserves_field_and_form_messages():
    form = ExampleForm({"name": ""})
    assert not form.is_valid()

    payload = validation_errors(form)

    assert payload["fields"]["name"] == ["This field is required."]
    assert payload["form"] == ["The record changed while you were editing."]


def test_list_response_uses_camel_case_and_clamps_values():
    payload = list_response(
        [{"id": "one"}],
        page=9,
        page_size=20,
        total_items=21,
        filters={"q": "house"},
        sort_key="updated",
        sort_direction="unexpected",
    )

    assert payload["pagination"] == {
        "page": 2,
        "pageSize": 20,
        "totalItems": 21,
        "totalPages": 2,
        "hasNext": False,
        "hasPrevious": True,
    }
    assert payload["filters"] == {"q": "house"}
    assert payload["sort"] == {"key": "updated", "direction": "asc"}
