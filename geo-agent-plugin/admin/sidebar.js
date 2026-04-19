( function () {
  'use strict';

  const { registerPlugin }                         = wp.plugins;
  const { PluginSidebar, PluginSidebarMoreMenuItem } = wp.editPost;
  const { PanelBody, PanelRow, Button, Spinner, Notice, TextareaControl, SelectControl, Dashicon } = wp.components;
  const { useSelect, useDispatch }                 = wp.data;
  const { useState, useEffect }                    = wp.element;
  const apiFetch                                   = wp.apiFetch;

  const { nonce, apiBase, defaultStrategy, hasApiKey } = window.geoAgentData || {};

  // Strategian suomenkieliset nimet
  const strategyLabels = {
    hybrid : '⚡ Hybrid — GEO + SEO',
    geo    : '🌐 GEO — AI-siteerattavuus',
    seo    : '🔍 SEO — hakukonenäkyvyys',
    none   : '✅ Ei optimointitarvetta',
    auto   : 'Auto',
  };

  function GeoAgentPanel() {
    const postId   = useSelect( s => s('core/editor').getCurrentPostId() );
    const title    = useSelect( s => s('core/editor').getEditedPostAttribute('title') );
    const content  = useSelect( s => s('core/editor').getEditedPostContent() );
    const { editPost, savePost } = useDispatch('core/editor');

    const [phase, setPhase]                 = useState('idle');   // idle | analyzing | analyzed | optimizing | optimized | publishing
    const [error, setError]                 = useState(null);
    const [notice, setNotice]               = useState(null);
    const [analysis, setAnalysis]           = useState(null);
    const [optimizedContent, setOptimized]  = useState('');
    const [hasBackup, setHasBackup]         = useState(false);
    const [backupDate, setBackupDate]       = useState(null);

    // Tarkista varmuuskopion tila sivua avattaessa
    useEffect(() => {
      if (!postId) return;
      apiFetch({
        path    : `${apiBase}/backup-status?post_id=${postId}`,
        headers : { 'X-WP-Nonce': nonce },
      }).then(r => {
        setHasBackup(r.has_backup);
        setBackupDate(r.backup_date);
      }).catch(() => {});
    }, [postId]);

    function handleAnalyze() {
      setError(null);
      setNotice(null);
      setPhase('analyzing');
      apiFetch({
        path   : `${apiBase}/analyze`,
        method : 'POST',
        headers: { 'X-WP-Nonce': nonce, 'Content-Type': 'application/json' },
        data   : { post_id: postId, content, title },
      }).then(r => {
        setAnalysis(r);
        setPhase('analyzed');
      }).catch(e => {
        setError(e.message || 'Analyysi epäonnistui.');
        setPhase('idle');
      });
    }

    function handleOptimize() {
      if (!analysis) return;
      setError(null);
      setPhase('optimizing');
      apiFetch({
        path   : `${apiBase}/optimize`,
        method : 'POST',
        headers: { 'X-WP-Nonce': nonce, 'Content-Type': 'application/json' },
        data   : {
          post_id  : postId,
          content,
          title,
          strategy : analysis.strategy,
          seo_fixes: analysis.seo?.fixes || [],
        },
      }).then(r => {
        setOptimized(r.optimized_content);
        setPhase('optimized');
      }).catch(e => {
        setError(e.message || 'Optimointi epäonnistui.');
        setPhase('analyzed');
      });
    }

    function handlePublish() {
      setPhase('publishing');
      apiFetch({
        path   : `${apiBase}/publish`,
        method : 'POST',
        headers: { 'X-WP-Nonce': nonce, 'Content-Type': 'application/json' },
        data   : { post_id: postId, optimized_content: optimizedContent },
      }).then(() => {
        setNotice('✅ Sivu julkaistu onnistuneesti.');
        setPhase('idle');
        setAnalysis(null);
        setOptimized('');
        setHasBackup(true);
        setBackupDate(new Date().toLocaleString('fi-FI'));
      }).catch(e => {
        setError(e.message || 'Julkaisu epäonnistui.');
        setPhase('optimized');
      });
    }

    function handleRollback() {
      if (!confirm('Palautetaanko sivu varmuuskopiosta? Nykyiset muutokset katoavat.')) return;
      apiFetch({
        path   : `${apiBase}/rollback`,
        method : 'POST',
        headers: { 'X-WP-Nonce': nonce, 'Content-Type': 'application/json' },
        data   : { post_id: postId },
      }).then(() => {
        setNotice('↩️ Sivu palautettu varmuuskopiosta.');
        setHasBackup(false);
        setBackupDate(null);
        setPhase('idle');
      }).catch(e => {
        setError(e.message || 'Rollback epäonnistui.');
      });
    }

    const isBusy = ['analyzing', 'optimizing', 'publishing'].includes(phase);

    return wp.element.createElement(
      PluginSidebar,
      { name: 'geo-agent-sidebar', title: 'GEO Agent', icon: 'chart-line' },

      // API key -varoitus
      !hasApiKey && wp.element.createElement(
        Notice, { status: 'warning', isDismissible: false },
        'API key puuttuu. Lisää se ',
        wp.element.createElement('a', { href: '/wp-admin/options-general.php?page=geo-agent-settings' }, 'asetuksiin'),
        '.'
      ),

      // Virhe / ilmoitus
      error && wp.element.createElement( Notice, { status: 'error',   isDismissible: true, onRemove: () => setError(null)  }, error  ),
      notice && wp.element.createElement( Notice, { status: 'success', isDismissible: true, onRemove: () => setNotice(null) }, notice ),

      // Analyysi-osio
      wp.element.createElement(
        PanelBody, { title: 'Analyysi', initialOpen: true },

        phase === 'idle' && wp.element.createElement(
          Button, { variant: 'primary', onClick: handleAnalyze, disabled: !hasApiKey || isBusy },
          '🔍 Analysoi sivu'
        ),

        phase === 'analyzing' && wp.element.createElement( 'div', { className: 'geo-busy' },
          wp.element.createElement( Spinner ),
          ' Analysoidaan...'
        ),

        analysis && wp.element.createElement(
          'div', { className: 'geo-analysis' },

          // GEO-pisteet
          wp.element.createElement( 'div', { className: 'geo-score' },
            wp.element.createElement( 'span', { className: 'geo-score__label' }, 'GEO-pisteet' ),
            wp.element.createElement( 'span', {
              className: `geo-score__value geo-score__value--${analysis.geo_score >= 7 ? 'good' : analysis.geo_score >= 4 ? 'medium' : 'bad'}`
            }, `${analysis.geo_score}/10` )
          ),

          // Strategia
          wp.element.createElement( 'div', { className: 'geo-strategy' },
            wp.element.createElement( 'strong', null, 'Strategia: ' ),
            strategyLabels[analysis.strategy] || analysis.strategy
          ),
          wp.element.createElement( 'p', { className: 'geo-reasoning' }, analysis.reasoning ),

          // SEO-signaalit
          analysis.seo && wp.element.createElement(
            'div', { className: 'geo-seo-signals' },
            wp.element.createElement( 'strong', null, 'SEO-signaalit' ),
            wp.element.createElement( 'ul', null,
              seoRow('Sanamäärä', `${analysis.seo.word_count} sanaa`, analysis.seo.word_count >= 600),
              seoRow('Focus keyword H2:ssa', analysis.seo.focus_keyword, analysis.seo.keyword_in_h2),
              seoRow('Sisäiset linkit', `${analysis.seo.internal_link_count} kpl`, analysis.seo.internal_link_count >= 2),
              seoRow('Meta description', analysis.seo.has_meta_desc ? 'OK' : 'Puuttuu', analysis.seo.has_meta_desc),
            )
          ),

          // GEO-ongelmat
          analysis.geo_issues?.length > 0 && wp.element.createElement(
            'div', { className: 'geo-issues' },
            wp.element.createElement( 'strong', null, 'GEO-ongelmat' ),
            wp.element.createElement( 'ul', null,
              ...analysis.geo_issues.map( (issue, i) =>
                wp.element.createElement( 'li', { key: i, className: 'geo-issue' }, issue )
              )
            )
          ),

          // Optimoi-nappi (jos ei jo optimoitu)
          analysis.strategy !== 'none' && phase === 'analyzed' && wp.element.createElement(
            'div', { className: 'geo-actions' },
            wp.element.createElement(
              Button, { variant: 'primary', onClick: handleOptimize, disabled: isBusy },
              `✍️ Optimoi (${analysis.strategy.toUpperCase()})`
            ),
            wp.element.createElement(
              Button, { variant: 'secondary', onClick: handleAnalyze, disabled: isBusy },
              'Analysoi uudelleen'
            )
          ),

          phase === 'optimizing' && wp.element.createElement( 'div', { className: 'geo-busy' },
            wp.element.createElement( Spinner ),
            ' Optimoidaan Claudella...'
          ),
        ),
      ),

      // Diff-osio
      optimizedContent && wp.element.createElement(
        PanelBody, { title: 'Optimoitu sisältö', initialOpen: true },
        wp.element.createElement( 'p', { className: 'geo-diff-hint' },
          'Tarkista optimoitu sisältö ennen julkaisua.'
        ),
        wp.element.createElement( TextareaControl, {
          label   : 'Optimoitu teksti',
          value   : optimizedContent,
          rows    : 12,
          onChange: setOptimized,
        }),
        phase === 'optimized' && wp.element.createElement(
          'div', { className: 'geo-actions' },
          wp.element.createElement(
            Button, { variant: 'primary', onClick: handlePublish, disabled: isBusy },
            '✅ Hyväksy ja julkaise'
          ),
          wp.element.createElement(
            Button, { variant: 'secondary', isDestructive: true, onClick: () => { setOptimized(''); setPhase('analyzed'); } },
            '✕ Hylkää'
          ),
        ),
        phase === 'publishing' && wp.element.createElement( 'div', { className: 'geo-busy' },
          wp.element.createElement( Spinner ),
          ' Julkaistaan...'
        ),
      ),

      // Rollback-osio
      hasBackup && wp.element.createElement(
        PanelBody, { title: '↩️ Varmuuskopio', initialOpen: false },
        backupDate && wp.element.createElement( 'p', { className: 'geo-backup-date' },
          `Otettu: ${backupDate}`
        ),
        wp.element.createElement(
          Button, { variant: 'secondary', isDestructive: true, onClick: handleRollback },
          'Palauta varmuuskopiosta'
        ),
      ),
    );
  }

  function seoRow(label, value, ok) {
    return wp.element.createElement(
      'li', { key: label, className: `geo-seo-row geo-seo-row--${ok ? 'ok' : 'fail'}` },
      wp.element.createElement( 'span', { className: 'geo-seo-row__icon' }, ok ? '✅' : '❌' ),
      wp.element.createElement( 'span', { className: 'geo-seo-row__label' }, label ),
      wp.element.createElement( 'span', { className: 'geo-seo-row__value' }, value ),
    );
  }

  registerPlugin( 'geo-agent', { render: GeoAgentPanel } );

}() );
