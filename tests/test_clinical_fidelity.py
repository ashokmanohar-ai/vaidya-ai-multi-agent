from vaidya.fidelity import clinical_fidelity_warnings

def test_numeric_mismatch_flagged():
    flags=clinical_fidelity_warnings('Temperature is 102 F', [{'text':'Temperature 104 F'}])
    assert '104' in ' '.join(flags)

def test_laterality_unsupported_flagged():
    flags=clinical_fidelity_warnings('Mass observed in tissue', [{'text':'Right mass observed'}])
    assert any('right' in f for f in flags)

def test_translation_dropped_numeric_flagged():
    flags=clinical_fidelity_warnings('Tissue 13 mm', [{'text':'Tissue size'}],'Tissue size observed')
    assert any('13' in f for f in flags)

def test_matching_numbers_not_flagged():
    flags=clinical_fidelity_warnings('Temperature 102 F',[{'text':'Temperature 102 F'}])
    assert not flags
