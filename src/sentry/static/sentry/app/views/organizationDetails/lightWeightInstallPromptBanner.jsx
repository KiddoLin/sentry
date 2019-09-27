import PropTypes from 'prop-types';
import React from 'react';

import InstallPromptBanner from 'app/views/organizationDetails/installPromptBanner';

import SentryTypes from 'app/sentryTypes';
import withApi from 'app/utils/withApi';
import withTeamProjects from 'app/utils/withTeamProjects';
import withUsersTeams from 'app/utils/withUsersTeams';

class LightWeightInstallPromptBanner extends React.Component {
  static propTypes = {
    organization: PropTypes.object,
    projects: PropTypes.arrayOf(SentryTypes.Project),
    loadingProjects: PropTypes.bool,
  };

  render() {
    if (this.props.loadingProjects) {
      return null;
    }
    return <InstallPromptBanner detailed={0} {...this.props} />;
  }
}

export default withApi(withUsersTeams(withTeamProjects(LightWeightInstallPromptBanner)));
