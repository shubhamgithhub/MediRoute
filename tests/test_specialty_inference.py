from mediroute.backend.main import infer_medical_context


def test_blurry_vision_maps_to_ophthalmology():
    result = infer_medical_context("My vision is blurry")

    assert result["relevantSpecialty"] == "Ophthalmology"
    assert result["careCategory"] == "Eye Care"
