# Co se děje pri tréninku modelu?

## Training -přehled

- vytvoření modelu
- transformace dat do podoby vhodné pro neuronovou síť
    - tj. vstupy z <-1,1>, častěji <0,1>
    - v aktuálním modelu se používá one-hot encoding znaků z latinky
- rozdělení dat na train a validaci
- trénink přes model.fit
    - shuffle data po každé epoše

Praktické problémy
- one-hot encodovaná data se nevejdou do paměti
    -> generátory a model.fit_generator
- model je sice teoreticky nezávislý na délce vstupu, ale pro účely tréninku a paralelizace je třeba mít konstantní délku vstupu
    - proto se musí paddovat krátké vstupy a samplovat dlouhé
- callbacky umožňují ukládat data v průběhu tréninku (checkpointy modelu, statistiky, atd.)

## Training -detaily

(Odskočení znamená větší detail k bodu nad)

#### create_cnn_class

- vytvoření klasifikačního modelu

#### nahrání natrénovaných vah

#### get_generators

- load dat z picklu
- rozdělení dat na trénovací a validační
    - data už jsou shufflovaná, takže jde jen o rozdělení v poměru dle configu
- vytvoření generátorů pro trénink a validaci
    - protože celá data v reprezentaci vhodné pro trénink se nevejdou najednou do paměti

    ##### create_data
    - vytvoří se batch náhodných čísel pro celou trénovací epochu, což je rychlejší než je generovat po jednom
        - tato čísla jsou indexy, na kterých se začínají brát posty z dat, z nichž se generují trénovací batche
        - po vygenerování těchto náhodných indexů se celá trénovací data zamíchají
            - aby 2 batche z různých epoch, vygenerované ze stejného počátečního indexu, byly složené z různých dat
        - tohle všechno je důležité kvůli paralelizaci generátorů (aby negenerovaly všechny stejné batche)
            - při validaci se data neshufflují

        ###### one_hot_encode_post
        - transformace postu do tvaru vhodného pro neuronovou síť
        - nejdřív se post nasampluje tak, aby měl maximálně délku definovanou v configu
            - sample je udělaný tak, aby vždy obsahoval celý "title" postu
            - při tréninku a validaci se zbytek postu sampluje uniformě
            - ve voterovi se místo náhodného samplu vezme konec postu
        - pak se převede do číselné podoby
            - pokud je post kratší než délka z configu, tak je doplněn nulami zprava
        - číselná podoba se převede na one-hot encoding

#### get_callbacks
- vytvoření callbacků, které se volají při tréninku
    - na konci každého batche se ukládají hodnoty metrik
    - na konci každé trénovací epochy se dělá validace a ukládají se její výsledky
    - ukládání vah modelu

#### fit_generator
- volá si generátory ve 4 paralelních vláknech, která plní frontu batchi trénovacích dat