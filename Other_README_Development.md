# TPD Dashboard — Adding New Content & Development

> How to add new slides, transforms, sections, and follow development rules.

---

## Adding a New Slide

1. Create `pipeline/slides/slide_XX_name.py`
2. Set required module attributes:
   ```python
   SECTION = "experience"  # or: default, diagnostics, assumptions, pipeline_audit
   ORDER = 50              # multiples of 10
   LABEL = "My Slide Title"
   ```
3. Implement the render function:
   ```python
   def render(data_store, tab_index=0):
       # Read data from data_store
       # Create Streamlit UI elements
       pass
   ```
4. Run `streamlit run app.py` — your slide appears automatically!

---

## Adding a New Transform

1. Create `pipeline/transforms/transform_XX_name.py`
2. Include full docstring:
   ```python
   """
   transform_XX_name.py — Brief description.
   
   Input :  input_key (from transform_YY)
   Output: output_key (used by slide_ZZ)
   """
   ```
3. Implement the compute function:
   ```python
   import streamlit as st
   
   @st.cache_data(show_spinner=False, ttl=None)
   def compute(_data_store, **kwargs):
       df = _data_store.get("input_key")
       if df is None:
           return {"output_key": pd.DataFrame()}
       df = df.copy()
       # ... your logic ...
       return {"output_key": result}
   ```
4. The transform runs automatically on next pipeline execution.

---

## Adding a New Section

1. Create `pipeline/sections/section_yourname.py`
2. Define section metadata and slide mappings
3. Update `pipeline/sections/__init__.py` to include your section

---

## Development Rules (Top 5)

Full list in [`DEVELOPMENT_RULES.md`](DEVELOPMENT_RULES.md).

1. **NEVER mutate cached data in-place** — Always use `.copy()` before modifying DataFrames
2. **ALWAYS use `.get()` with None checks** — Never access `data_store` with bracket notation
3. **Transforms MUST accept `**kwargs`** — Required for cache invalidation
4. **Slides MUST accept `tab_index` parameter** — Required for tabbed views
5. **Slides are PURE PRESENTATION** — Business logic belongs in transforms

---

## AI-Assisted Development

This project is **AI-friendly**:
- Read `DEVELOPMENT_RULES.md` before making changes
- Follow templates in existing slides/transforms
- Use `python auto_generate_docs.py` to document changes
- Test all sections after modifications

See `AI_GUIDE.md` for step-by-step prompts.

---

## Maintenance Workflow

1. **Add new slide/transform**: Drop Python file in appropriate folder
2. **Run dashboard**: Streamlit auto-discovers new modules
3. **Update docs**: Run `python auto_generate_docs.py`
4. **Rebuild wiki**: Run `python build_wiki.py && mkdocs build`
5. **Commit**: All changes tracked in Git
