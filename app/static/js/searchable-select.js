/**
 * SearchableSelect — lightweight searchable dropdown
 * Replaces a <select> or a text <input> with a search-filtered results UI.
 * Reuses jf-search-* classes from job-flow.css.
 *
 * Usage (from <select>):
 *   new SearchableSelect(document.querySelector('select[name=service_id]'))
 *
 * Usage (from a static list):
 *   new SearchableSelect(inputEl, { items: ['Toyota', 'Maruti', …] })
 */
class SearchableSelect {
  constructor(targetEl, opts = {}) {
    this.target     = targetEl;
    this.items      = opts.items       || null;   // [{label, value}] or ['string', …]
    this.placeholder = opts.placeholder || 'Search…';
    this.maxResults  = opts.maxResults  || 80;
    this.onChange    = opts.onChange    || null;
    this._selectedLabel = '';
    this._build();
  }

  _build() {
    // Collect items from <select> options if not provided
    if (!this.items && this.target.tagName === 'SELECT') {
      this.items = Array.from(this.target.options)
        .filter(o => o.value)
        .map(o => ({ label: o.textContent.trim(), value: o.value }));
    } else if (this.items && typeof this.items[0] === 'string') {
      this.items = this.items.map(s => ({ label: s, value: s }));
    }

    // Wrapper
    const wrap = document.createElement('div');
    wrap.className = 'jf-search-wrap ss-wrap';
    wrap.style.position = 'relative';

    // Icon
    const icon = document.createElement('i');
    icon.className = 'ti ti-search jf-search-icon';

    // Text input
    this.input = document.createElement('input');
    this.input.type        = 'text';
    this.input.className   = 'jf-search-input';
    this.input.placeholder = this.placeholder;
    this.input.autocomplete = 'off';

    // Clear button
    this.clearBtn = document.createElement('button');
    this.clearBtn.type      = 'button';
    this.clearBtn.className = 'ss-clear';
    this.clearBtn.innerHTML = '<i class="ti ti-x"></i>';
    this.clearBtn.style.cssText = [
      'position:absolute', 'right:10px', 'top:50%', 'transform:translateY(-50%)',
      'border:none', 'background:none', 'color:#94a3b8', 'cursor:pointer',
      'padding:0', 'line-height:1', 'display:none', 'font-size:.875rem'
    ].join(';');

    // Dropdown
    this.dropdown = document.createElement('div');
    this.dropdown.className = 'jf-search-results';

    wrap.append(icon, this.input, this.clearBtn, this.dropdown);

    // Hide original element, insert wrapper before it
    this.target.style.display = 'none';
    this.target.parentNode.insertBefore(wrap, this.target);

    this._bindEvents();
  }

  _bindEvents() {
    this.input.addEventListener('focus', () => this._render(this.input.value));
    this.input.addEventListener('input', () => {
      this._render(this.input.value);
      this.clearBtn.style.display = this.input.value ? '' : 'none';
    });

    this.clearBtn.addEventListener('click', () => {
      this.input.value = '';
      this._setValue('', '');
      this.clearBtn.style.display = 'none';
      this.dropdown.classList.remove('show');
      this.input.focus();
    });

    document.addEventListener('click', e => {
      if (!this.input.contains(e.target) && !this.dropdown.contains(e.target)) {
        this.dropdown.classList.remove('show');
        // If nothing selected, restore label
        if (!this._getValue()) this.input.value = '';
        else this.input.value = this._selectedLabel;
      }
    });
  }

  _render(q) {
    const query = (q || '').toLowerCase().trim();
    const filtered = query
      ? this.items.filter(i => i.label.toLowerCase().includes(query))
      : this.items;

    const visible = filtered.slice(0, this.maxResults);
    this.dropdown.innerHTML = '';

    if (!visible.length) {
      this.dropdown.innerHTML = '<div style="padding:.75rem 1rem;color:#94a3b8;font-size:.875rem;">No results</div>';
    } else {
      visible.forEach(item => {
        const el = document.createElement('div');
        el.className = 'jf-search-item';

        // Highlight matched portion
        const label = query
          ? item.label.replace(new RegExp(`(${query})`, 'gi'), '<mark style="background:#fde68a;border-radius:2px;padding:0 1px;">$1</mark>')
          : item.label;
        el.innerHTML = `<span style="font-size:.9rem;">${label}</span>`;

        el.addEventListener('mousedown', e => {
          e.preventDefault(); // prevent blur before click
          this._selectItem(item);
        });
        this.dropdown.appendChild(el);
      });

      if (filtered.length > this.maxResults) {
        const more = document.createElement('div');
        more.style.cssText = 'padding:.5rem 1rem;font-size:.75rem;color:#94a3b8;';
        more.textContent = `${filtered.length - this.maxResults} more — type to narrow`;
        this.dropdown.appendChild(more);
      }
    }

    this.dropdown.classList.add('show');
  }

  _selectItem(item) {
    this.input.value = item.label;
    this._selectedLabel = item.label;
    this._setValue(item.value, item.label);
    this.clearBtn.style.display = '';
    this.dropdown.classList.remove('show');
    if (this.onChange) this.onChange(item);
  }

  _setValue(value, label) {
    if (this.target.tagName === 'SELECT') {
      this.target.value = value;
    } else {
      this.target.value = value;
    }
  }

  _getValue() {
    return this.target.tagName === 'SELECT' ? this.target.value : this.target.value;
  }

  /** Programmatically set a value */
  setValue(value) {
    const item = this.items.find(i => String(i.value) === String(value));
    if (item) this._selectItem(item);
  }
}

/* ── Top Indian/global car manufacturers ────────────────────────── */
const CAR_MANUFACTURERS = [
  'Aston Martin','Audi','BMW','BYD','Bentley','Chevrolet','Chrysler','Citroen',
  'Datsun','Ferrari','Fiat','Force Motors','Ford','Genesis','Honda','Hyundai',
  'Isuzu','Jaguar','Jeep','Kia','Lamborghini','Land Rover','Lexus','Maserati',
  'Mahindra','Mercedes-Benz','MG','Mini','Mitsubishi','Nissan','Ola Electric',
  'Opel','Peugeot','Porsche','Renault','Rolls-Royce','Skoda','Ssangyong',
  'Stellantis','Subaru','Suzuki','Tata Motors','Tesla','Toyota','Volkswagen',
  'Volvo','Maruti Suzuki','Premier','Hindustan Motors','Bajaj Auto',
];
CAR_MANUFACTURERS.sort();
